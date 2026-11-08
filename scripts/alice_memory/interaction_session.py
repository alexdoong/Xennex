"""One owner routes live human interactions into existing cognitive queues."""
import copy

from .concept_memory import scalar
from .interaction_inbox import validate, digest, identity, integer, canonical

LIMIT = 32
STATES = ('queued', 'running', 'awaiting_reply', 'completed', 'failed')
FIELDS = {'request', 'request_sha256', 'issued', 'expires', 'lane', 'job', 'status', 'result', 'revision', 'published'}
LANES = {'name': 'native_namings', 'ask': 'native_queries',
         'report': 'native_statements', 'meaning': 'native_meaning_queries',
         'relate': 'native_statements', 'correct': 'native_statements', 'recall': 'native_meaning_queries',
         'feedback': 'native_feedbacks', 'talk': 'dialogues'}
QUERIES = ('native_queries', 'native_meaning_queries', 'dialogues')
LEARNING = ('native_namings', 'native_statements', 'native_feedbacks')


def result(status, *, error=None, question=None, learning=None, data=None):
    return {'status': status, 'error': error, 'question': question, 'learning': learning, 'data': data}


def dialogue_data(job):
    from .reference_language import phrases
    from .dialogue_recall import memory as selected_memory
    memory = selected_memory(job['context'])
    return {'evidence': copy.deepcopy(job['context']), 'proposal': copy.deepcopy(job['proposal']),
            'memory_text': None if memory is None else phrases(memory)[0]}


class InteractionSession:
    def __init__(self, owner):
        self.owner = owner
        self.stream_id = None
        self.last_sequence = -1
        self.records = {}
        from .dialogue import DialogueLane
        self.dialogues = None if owner.teaching is None else DialogueLane(owner)

    def configure(self, inbox):
        if self.stream_id is not None and self.stream_id != inbox.stream_id:
            raise ValueError('Interaction session belongs to another inbox.')
        self.stream_id = inbox.stream_id

    def ingest(self, request):
        validate(request)
        if request['stream_id'] != self.stream_id:
            raise ValueError('Interaction belongs to another source stream.')
        prior = self.records.get(request['id'])
        if prior is not None:
            if prior['request_sha256'] != digest(request):
                raise ValueError('Interaction identity was reused with different content.')
            return True
        if request['sequence'] <= self.last_sequence:
            return False
        self.prune()
        if len(self.records) >= LIMIT:
            return False
        now = self.owner.clock
        self.records[request['id']] = {'request': copy.deepcopy(request), 'request_sha256': digest(request),
            'issued': now, 'expires': now + 300., 'lane': None, 'job': None,
            'status': 'queued', 'result': None, 'revision': 0, 'published': 0}
        self.last_sequence = request['sequence']
        return True

    def prune(self):
        if len(self.records) < LIMIT:
            return
        removable = sorted((record for record in self.records.values()
            if record['status'] in ('completed', 'failed') and record['published'] == record['revision']
            and not any((other['request']['payload'].get('reply_to') or other['request']['payload'].get('about')) == record['request']['id']
                        and (other['status'] not in ('completed', 'failed') or other['published'] < other['revision'])
                        for other in self.records.values())),
            key=lambda record: record['request']['sequence'])
        for record in removable[:max(1, len(self.records) - LIMIT + 1)]:
            del self.records[record['request']['id']]

    def finish(self, record, value):
        if record['result'] == value:
            return
        record.update(status=value['status'], result=copy.deepcopy(value), revision=record['revision'] + 1)

    def selected_frame(self, frame):
        stream = self.owner.native_stream
        if stream.stream_id != frame['stream_id']:
            raise ValueError('Naming frame belongs to another sensory stream.')
        matches = [trace for trace in self.owner.native.moments.traces if trace['source_context'] is not None
            and trace['source_context']['stream_id'] == frame['stream_id']
            and trace['source_context']['source_sequence'] == frame['sequence']]
        if len(matches) == 1:
            return matches[0]['id']
        if len(matches) > 1:
            raise ValueError('Sensory frame has ambiguous retained moments.')
        pending = any(job['source_sequence'] == frame['sequence'] and job['status'] not in ('completed', 'ignored', 'failed') for job in stream.jobs.values())
        if pending or frame['sequence'] > stream.last_source_sequence:
            return None
        raise ValueError('Selected sensory frame was not attended or is no longer retained.')

    def report_source(self, identifier):
        parent = self.records.get(identifier)
        if parent is None or parent['request']['action'] not in ('report', 'relate', 'correct'):
            raise ValueError('Reference does not point to a retained reporting interaction.')
        if parent['status'] in ('queued', 'running'):
            return None
        if parent['status'] != 'completed' or not parent['result']['learning'] or parent['result']['learning'].get('kind') != 'reported_interpretation':
            raise ValueError('Reference requires a learned external report.')
        version = parent['result']['learning']['version']
        memory = self.owner.native.interpretations
        integer(version, 0, len(memory.records) - 1)
        source = memory.records[version]
        from .context_report_language import sha
        if source['source_sha256'] != sha(parent['request']['payload']['text']) or source['origin'] != 'person':
            raise ValueError('Referenced message lost its original external report source.')
        return source

    def received_text(self, payload):
        from .dialogue_language import sha, validate_input
        frame, stream = payload['frame'], self.owner.native_stream
        if stream.stream_id != frame['stream_id']:
            raise ValueError('Dialogue text belongs to a different sensory stream.')
        job = next((item for item in [*stream.jobs.values(), *stream.deliveries] if item['source_sequence'] == frame['sequence']), None)
        if job is None:
            if frame['sequence'] > stream.last_source_sequence:
                return None
            raise ValueError('Dialogue text receipt is no longer available.')
        if job['status'] not in ('completed', 'ignored', 'failed'):
            return None
        files = job['manifest']['files']
        if job['status'] == 'failed' or job['manifest']['origin'] != 'person' or len(files) != 1 or files[0]['modality'] != 'text' or files[0]['sha256'] != sha(payload['text']):
            raise ValueError('Dialogue requires the exact externally received text signal.')
        received = {'frame': copy.deepcopy(frame), 'sha256': files[0]['sha256'],
                    'acquired': job['result']['encoded'] > 0, 'moment_ref': copy.deepcopy(job['moment_ref'])}
        validate_input(received, payload['text'])
        return received

    def correction_binding(self, payload):
        source = self.report_source(payload['reply_to'])
        if source is None:
            return None
        memory = self.owner.native.interpretations
        version = source['id']
        relation = memory.relations[source['relation']]
        if version not in memory.versions(source['moment'], relation):
            raise ValueError('The referenced report has already been replaced.')
        return {'moment_ref': copy.deepcopy(source['moment_ref']), 'received_at': source['acquired_at'],
                'selected': True, 'relation': relation, 'corrects': [version]}

    def dispatch(self, record):
        request = record['request']
        payload, action = request['payload'], request['action']
        try:
            if action == 'name':
                moment = payload['moment']
                if payload['frame'] is not None:
                    moment = self.selected_frame(payload['frame'])
                    if moment is None:
                        return
                number = self.owner.submit_native_name(payload['text'], payload['focus'], moment)
                record.update(lane='native_namings', job=number, status='running')
            elif action == 'ask':
                number = self.owner.submit_native_question(payload['text'])
                record.update(lane='native_queries', job=number, status='running')
            elif action == 'report':
                number = self.owner.submit_native_statement(payload['text'])
                record.update(lane='native_statements', job=number, status='running')
            elif action == 'relate':
                moment = payload['moment']
                if payload['frame'] is not None:
                    moment = self.selected_frame(payload['frame'])
                    if moment is None:
                        return
                number = self.owner.submit_context_report(payload['text'], moment)
                record.update(lane='native_statements', job=number, status='running')
            elif action == 'correct':
                binding = self.correction_binding(payload)
                if binding is None:
                    return
                number = self.owner.submit_context_report(payload['text'], correction=binding)
                record.update(lane='native_statements', job=number, status='running')
            elif action == 'meaning':
                number = self.owner.submit_native_meaning_question(payload['text'])
                record.update(lane='native_meaning_queries', job=number, status='running')
            elif action == 'recall':
                source = self.report_source(payload['about'])
                if source is None:
                    return
                binding = {'version': source['id'], 'moment_ref': copy.deepcopy(source['moment_ref']),
                           'relation': self.owner.native.interpretations.relations[source['relation']]}
                number = self.owner.submit_reference_question(payload['text'], binding)
                record.update(lane='native_meaning_queries', job=number, status='running')
            elif action == 'feedback':
                if self.owner.native_feedbacks is None:
                    raise ValueError('Attention feedback requires a language coordinator.')
                if len(self.owner.native_feedbacks.jobs) >= 4:
                    return
                number = self.owner.submit_native_feedback(payload['text'], payload['action'])
                record.update(lane='native_feedbacks', job=number, status='running')
            elif action == 'talk':
                if self.dialogues is None:
                    raise ValueError('Dialogue requires a language coordinator.')
                received = self.received_text(payload)
                if received is None or len(self.dialogues.jobs) >= 4:
                    return
                source = None if payload['about'] is None else self.report_source(payload['about'])
                if payload['about'] is not None and source is None:
                    return
                binding = None if source is None else {'version': source['id'], 'moment_ref': copy.deepcopy(source['moment_ref']),
                            'relation': self.owner.native.interpretations.relations[source['relation']]}
                number = self.dialogues.submit(payload['text'], received, binding, payload['about'])
                record.update(lane='dialogues', job=number, status='running')
            elif action == 'recall_feedback':
                from .recall_feedback import apply
                self.finish(record, result('completed', **apply(self, record)))
            else:
                parent = self.records.get(payload['reply_to'])
                if parent is None or parent['status'] != 'awaiting_reply' or parent['lane'] != 'native_namings' or parent['job'] is None:
                    raise ValueError('Reply does not refer to an unresolved naming interaction.')
                learning = self.owner.reply_native_name(parent['job'], payload['word'], payload['focus'])
                self.finish(record, result('completed', learning=learning))
        except ValueError as error:
            # A full cognitive queue applies backpressure instead of dropping
            # an input; other invalid contexts are explicit terminal responses.
            lane = None if action == 'recall_feedback' else getattr(self.owner, LANES.get(action, 'native_namings'))
            if lane is not None and len(lane.jobs) >= 4:
                return
            self.finish(record, result('failed', error=str(error)[:2048]))

    def poll(self):
        for record in self.records.values():
            self.refresh(record)
        for record in sorted(self.records.values(), key=lambda item: item['request']['sequence']):
            if record['status'] == 'queued':
                if self.owner.clock > record['expires']:
                    self.finish(record, result('failed', error='interaction_expired'))
                else:
                    self.dispatch(record)
        for record in self.records.values():
            if record['status'] not in ('running', 'awaiting_reply'):
                continue
            lane = getattr(self.owner, record['lane'])
            job = lane.jobs.get(record['job'])
            if job is None:
                raise ValueError('Interaction lost its cognitive job.')
            if job['status'] not in lane.terminal:
                continue
            clarification = lane.clarification(job['id']) if record['lane'] == 'native_namings' else None
            if clarification is not None:
                self.finish(record, result('awaiting_reply', question=clarification['question']))
            elif job['status'] == 'completed':
                if record['lane'] in LEARNING:
                    self.finish(record, result('completed', learning=job['learning']))
                else:
                    data = dialogue_data(job) if record['lane'] == 'dialogues' else {key: copy.deepcopy(job[key]) for key in ('evidence', 'proposal')}
                    self.finish(record, result('completed', data=data))
            else:
                self.finish(record, result('failed', error=job['error'] or job['status']))

    def refresh(self, record):
        # A computed reply may wait for two disk generations. A correction or
        # forgotten cue during that interval must invalidate its old evidence.
        if record['status'] != 'completed' or record['lane'] not in QUERIES or record['published'] >= record['revision']:
            return
        lane = getattr(self.owner, record['lane'])
        job = lane.jobs[record['job']]
        evidence = job['context'] if record['lane'] == 'dialogues' else job['evidence']
        if lane.current(evidence):
            return
        job['revisions'] += 1
        lane.resolve(job)
        self.finish(record, result('running'))

    def publish(self, identifier, inbox, current, previous):
        record = self.records[identifier]
        self.refresh(record)
        if record['status'] not in ('completed', 'failed', 'awaiting_reply') or record['result'] is None or record['published'] >= record['revision']:
            return
        inbox.confirm(record, current, previous)
        record['published'] = record['revision']
        if record['status'] in ('completed', 'failed') and record['job'] is not None:
            lane = getattr(self.owner, record['lane'])
            lane.take(record['job'])
            record.update(lane=None, job=None)

    def snapshot(self):
        return {'format': 7, 'stream_id': self.stream_id, 'last_sequence': self.last_sequence,
                'records': copy.deepcopy(list(self.records.values())),
                'dialogues': None if self.dialogues is None else self.dialogues.snapshot()}

    def committed(self, captured, previous_snapshot, inbox, current, previous_commit):
        if previous_snapshot is None or previous_commit is None or current['file'] == previous_commit['file']:
            return
        prior = {item['request']['id']: item for item in previous_snapshot['records']}
        for item in captured['records']:
            identifier = item['request']['id']
            old, live = prior.get(identifier), self.records.get(identifier)
            if item['result'] is None or old is None or live is None:
                continue
            def key(record):
                return digest({name: record[name] for name in ('request_sha256', 'revision', 'result')})
            if key(item) == key(old) == key(live):
                self.publish(identifier, inbox, current, previous_commit)


def restore(payload, owner):
    fields = {'format', 'stream_id', 'last_sequence', 'records'}
    if isinstance(payload, dict) and payload.get('format') in (6, 7):
        fields.add('dialogues')
    if not isinstance(payload, dict) or set(payload) != fields or type(payload['format']) is not int or payload['format'] not in (1, 2, 3, 4, 5, 6, 7) or type(payload['last_sequence']) is not int or not -1 <= payload['last_sequence'] < 1000000 or not isinstance(payload['records'], list) or len(payload['records']) > LIMIT:
        raise ValueError('Invalid interaction session checkpoint.')
    if payload['stream_id'] is not None:
        identity(payload['stream_id'])
    elif payload['records'] or payload['last_sequence'] != -1:
        raise ValueError('Unbound interaction session contains requests.')
    session = InteractionSession(owner)
    if payload['format'] in (6, 7):
        from .dialogue import restore as restore_dialogues
        if session.dialogues is None and payload['dialogues'] is not None or session.dialogues is not None and payload['dialogues'] is None:
            raise ValueError('Dialogue queue changed its language owner.')
        session.dialogues = None if session.dialogues is None else restore_dialogues(payload['dialogues'], owner)
    session.stream_id, session.last_sequence = payload['stream_id'], payload['last_sequence']
    sequences = set()
    for original in payload['records']:
        record = copy.deepcopy(original)
        if not isinstance(record, dict) or set(record) != FIELDS:
            raise ValueError('Invalid saved interaction record.')
        request = validate(record['request'])
        if request['format'] > payload['format']:
            raise ValueError('Legacy session cannot assert a newer interaction protocol.')
        if payload['format'] == 1 and (request['format'] != 1 or request['action'] not in ('name', 'ask', 'reply')):
            raise ValueError('Legacy session cannot assert new interactions.')
        if payload['format'] == 2 and request['format'] > 2:
            raise ValueError('Version-two session cannot assert new interactions.')
        if payload['format'] == 3 and request['format'] > 3:
            raise ValueError('Version-three session cannot assert a referenced query.')
        if request['stream_id'] != session.stream_id or request['id'] in session.records or request['sequence'] > session.last_sequence or request['sequence'] in sequences or record['request_sha256'] != digest(request):
            raise ValueError('Saved interaction changed its source identity.')
        sequences.add(request['sequence'])
        scalar(record['issued'], 0, owner.clock)
        scalar(record['expires'], record['issued'] + 300., record['issued'] + 300.)
        integer(record['revision'], 0, 1000000)
        integer(record['published'], 0, record['revision'])
        if record['status'] not in STATES or record['lane'] not in (None, *LANES.values()):
            raise ValueError('Invalid saved interaction phase.')
        if (record['lane'] is None) != (record['job'] is None):
            raise ValueError('Saved interaction job binding is incomplete.')
        if record['job'] is not None:
            integer(record['job'], 1)
            lane = session.dialogues if record['lane'] == 'dialogues' else getattr(owner, record['lane'])
            if lane is None or record['job'] not in lane.jobs:
                raise ValueError('Saved interaction has no cognitive job.')
            job = lane.jobs[record['job']]
            if request['action'] not in LANES or job['question'] != request['payload']['text']:
                raise ValueError('Saved interaction changed its dispatched message.')
            expected_lane = LANES[request['action']]
            if record['lane'] != expected_lane:
                raise ValueError('Saved interaction changed its cognitive queue.')
            if request['action'] == 'feedback' and (job['action_id'] != request['payload']['action'] or job['origin'] != 'person'):
                raise ValueError('Feedback interaction changed its selected action or external source.')
            if request['action'] == 'talk':
                if job['input']['frame'] != request['payload']['frame'] or job['about'] != request['payload']['about']:
                    raise ValueError('Dialogue changed its received input frame.')
                parent = next((item for item in payload['records'] if item['request']['id'] == request['payload']['about']), None)
                if request['payload']['about'] is None and job['binding'] is not None or request['payload']['about'] is not None and (parent is None or parent['status'] != 'completed' or parent['request']['action'] not in ('relate', 'report', 'correct') or not isinstance(parent['result']['learning'], dict) or job['binding'] is None or parent['result']['learning'].get('version') != job['binding']['version']):
                    raise ValueError('Dialogue changed its selected reporting context.')
            if request['action'] == 'recall':
                parent = next((item for item in payload['records'] if isinstance(item, dict) and isinstance(item.get('request'), dict) and item['request'].get('id') == request['payload']['about']), None)
                learned = None if parent is None or not isinstance(parent.get('result'), dict) else parent['result'].get('learning')
                if parent is None or parent.get('status') != 'completed' or parent['request'].get('action') not in ('report', 'relate', 'correct') or not isinstance(learned, dict) or job.get('binding') is None or job['binding']['version'] != learned.get('version'):
                    raise ValueError('Referenced query changed its original reporting message.')
            if request['action'] in ('relate', 'correct'):
                binding = job['binding']
                if binding is None:
                    raise ValueError('Contextual interaction lost its original event binding.')
                if request['action'] == 'relate':
                    selected, frame = request['payload']['moment'], request['payload']['frame']
                    context = binding['moment_ref']['source_context']
                    if binding['corrects'] or (selected is not None and binding['moment_ref']['id'] != selected) or (frame is not None and (context is None or context['stream_id'] != frame['stream_id'] or context['source_sequence'] != frame['sequence'])):
                        raise ValueError('Contextual interaction changed its selected frame/moment.')
                else:
                    parent = next((item for item in payload['records'] if isinstance(item, dict) and isinstance(item.get('request'), dict) and item['request'].get('id') == request['payload']['reply_to']), None)
                    learned = None if parent is None or not isinstance(parent.get('result'), dict) else parent['result'].get('learning')
                    if parent is None or parent.get('status') != 'completed' or parent['request'].get('action') not in ('report', 'relate', 'correct') or not isinstance(learned, dict) or binding['corrects'] != [learned.get('version')]:
                        raise ValueError('Correction changed its original parent report.')
            if request['action'] == 'name':
                if job['focus'] != request['payload']['focus']:
                    raise ValueError('Saved naming interaction changed its requested focus.')
                selected = request['payload']['moment']
                if selected is not None and job['moment_ref']['id'] != selected:
                    raise ValueError('Saved naming interaction changed its selected memory.')
                frame = request['payload']['frame']
                context = job['moment_ref']['source_context']
                if frame is not None and (context is None or any(context[key] != frame[name] for key, name in (('stream_id', 'stream_id'), ('source_sequence', 'sequence')))):
                    raise ValueError('Saved naming interaction changed its selected sensory frame.')
        elif record['status'] in ('running', 'awaiting_reply'):
            raise ValueError('Live interaction has no job.')
        value = record['result']
        if value is None:
            if record['revision'] or record['published'] or record['status'] not in ('queued', 'running'):
                raise ValueError('Interaction phase lost its response.')
        elif not isinstance(value, dict) or set(value) != {'status', 'error', 'question', 'learning', 'data'} or value['status'] != record['status'] or not 1 <= record['revision'] or len(canonical(value).encode('utf-8')) > 65536:
            raise ValueError('Invalid saved interaction response.')
        if value is not None and any(value[key] is not None and (not isinstance(value[key], str) or len(value[key]) > 2048) for key in ('error', 'question')):
            raise ValueError('Interaction response contains invalid text.')
        if record['status'] == 'awaiting_reply' and (request['action'] != 'name' or record['lane'] != 'native_namings'):
            raise ValueError('Only naming interactions can await a word reply.')
        if record['status'] == 'completed' and request['action'] in ('report', 'relate', 'correct'):
            learning = value['learning']
            if not isinstance(learning, dict) or set(learning) != {'learned', 'version', 'kind', 'corrected', 'autobiographical_write'} or learning['learned'] is not True or learning['kind'] != 'reported_interpretation' or learning['autobiographical_write'] is not False:
                raise ValueError('Completed reporting interaction lost its learning provenance.')
            integer(learning['version'], 0, len(owner.native.interpretations.records) - 1)
            source = owner.native.interpretations.records[learning['version']]
            from .context_report_language import sha
            if source['source_sha256'] != sha(request['payload']['text']) or source['origin'] != 'person' or source['corrects'] != learning['corrected'] or not record['issued'] <= source['acquired_at'] <= record['expires']:
                raise ValueError('Completed reporting interaction changed its learned source/version.')
        if record['status'] == 'completed' and request['action'] == 'feedback':
            from .native_feedback import validate_receipt
            from .native_feedback_language import sha
            source = next((item for item in owner.native.attention.sources if item['id'] == request['payload']['action']), None)
            validate_receipt(value['learning'], source)
            if source['origin'] != 'person' or source['language'] is None or source['language']['message_sha256'] != sha(request['payload']['text']) or not record['issued'] <= source['acquired_at'] <= record['expires']:
                raise ValueError('Feedback interaction changed its learned external message.')
        if record['status'] == 'completed' and request['action'] == 'talk':
            from .dialogue_language import validate_expression
            context, proposal = value['data']['evidence'], value['data']['proposal']
            validate_expression(proposal, context, request['payload']['text'], proposal['model'])
            association = context.get('association')
            if association is not None and association['binding'] is not None:
                from .native_meaning_query import validate_binding
                validate_binding(association['binding'], owner.native, owner.clock)
            if association is not None and association.get('evocation') is not None:
                from .dialogue_evocation import validate_binding as validate_evocation_binding
                validate_evocation_binding(owner.native, association['evocation'])
            from .reference_language import phrases
            from .dialogue_recall import memory as selected_memory
            memory = selected_memory(context)
            expected_text = None if memory is None else phrases(memory)[0]
            if set(value['data']) != {'evidence', 'proposal', 'memory_text'} or value['data']['memory_text'] != expected_text:
                raise ValueError('Dialogue changed the owner-derived memory text.')
            if context['input']['frame'] != request['payload']['frame'] or context['about'] != request['payload']['about'] or value['learning'] is not None:
                raise ValueError('Dialogue response changed its received input or asserts teaching.')
        if record['status'] == 'completed' and request['action'] == 'recall_feedback':
            from .recall_feedback import validate_record
            validate_record(record, owner, payload['records'])
        if value is not None and record['job'] is not None and record['status'] == 'completed':
            if job['status'] != 'completed':
                raise ValueError('Interaction asserts completion before its cognitive job.')
            expected = result('completed', learning=job['learning']) if record['lane'] in LEARNING else result('completed', data=dialogue_data(job) if record['lane'] == 'dialogues' else {key: job[key] for key in ('evidence', 'proposal')})
            if value != expected:
                raise ValueError('Interaction response changed its cognitive result.')
        session.records[request['id']] = record
    return session
