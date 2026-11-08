"""Concept teaching and inquiry share the existing sensory/language clock."""
from __future__ import annotations

import copy

from .concept_memory import ConceptMemory, scalar, restore as restore_concepts
from .loop_checkpoint import atomic_write


class ConceptualMind:
    def __init__(self, agent):
        from .grounded_mind import GroundedMind
        from .language_coordinator import LanguageCoordinator
        if not isinstance(agent, (GroundedMind, LanguageCoordinator)):
            raise ValueError("Conceptual mind requires a grounded or language core.")
        self.agent = agent
        self.concepts = ConceptMemory()
        from .native_grounding import NativeGrounding
        self.native = NativeGrounding()
        self.native.clock = agent.clock
        self.native.moments.clock = agent.clock
        self.native.dynamics.clock = agent.clock
        self.native.links.clock = agent.clock
        from .native_stream import NativeStream
        self.native_stream = NativeStream(self)
        self.studies = []
        self.inquiries = {}
        self.next_study = 1
        from .concept_teaching import TeachingLane
        from .concept_query import ConceptQueryLane
        self.teaching = TeachingLane(agent, self.concepts) if isinstance(agent, LanguageCoordinator) else None
        self.concept_queries = ConceptQueryLane(agent, self.concepts) if self.teaching is not None else None
        from .native_query import NativeQueryLane
        self.native_queries = NativeQueryLane(agent, self.native) if self.teaching is not None else None
        from .native_statement import NativeStatementLane
        self.native_statements = NativeStatementLane(agent, self.native) if self.teaching is not None else None
        from .native_meaning_query import NativeMeaningQueryLane
        self.native_meaning_queries = NativeMeaningQueryLane(agent, self.native) if self.teaching is not None else None
        from .native_feedback import FeedbackLane
        self.native_feedbacks = FeedbackLane(agent, self) if self.teaching is not None else None
        from .native_name import NativeNameLane
        self.native_namings = NativeNameLane(agent, self.native) if self.teaching is not None else None
        from .interaction_session import InteractionSession
        self.interactions = InteractionSession(self)

    def __getattr__(self, name):
        return getattr(self.agent, name)

    def teach_concept(self, lesson):
        return self.concepts.teach(lesson, self.clock)

    @property
    def dialogues(self):
        return self.interactions.dialogues

    def request_study(self, options):
        self.concepts.choose_inquiry(options)  # Validate before changing the queue.
        if len(self.studies) + len(self.inquiries) >= 8 or self.next_study > 1000000:
            raise ValueError("Conceptual inquiry queue is full.")
        number = self.next_study
        self.studies.append({"id": number, "options": copy.deepcopy(options), "issued_at": self.clock})
        self.next_study += 1
        return number

    def tick(self, *args, **kwargs):
        self.interactions.poll()
        teaching_events = [] if self.teaching is None else self.teaching.poll()
        query_events = [] if self.concept_queries is None else self.concept_queries.poll()
        recall_events = [] if self.native_queries is None else self.native_queries.poll()
        statement_events = [] if self.native_statements is None else self.native_statements.poll()
        meaning_events = [] if self.native_meaning_queries is None else self.native_meaning_queries.poll()
        feedback_events = [] if self.native_feedbacks is None else self.native_feedbacks.poll()
        naming_events = [] if self.native_namings is None else self.native_namings.poll()
        dialogue_events = [] if self.dialogues is None else self.dialogues.poll()
        result = self.agent.tick(*args, **kwargs)
        self.native.advance(self.clock)
        native_events = self.native_stream.poll()
        if self.teaching is not None:
            teaching_events.extend(self.teaching.start())
            query_events.extend(self.concept_queries.start())
        if self.native_statements is not None:
            statement_events.extend(self.native_statements.start())
        if self.native_queries is not None:
            recall_events.extend(self.native_queries.start())
        if self.native_meaning_queries is not None:
            meaning_events.extend(self.native_meaning_queries.start())
        if self.native_feedbacks is not None:
            feedback_events.extend(self.native_feedbacks.start())
        if self.native_namings is not None:
            naming_events.extend(self.native_namings.start())
        if self.dialogues is not None:
            dialogue_events.extend(self.dialogues.start())
        native_events.extend(self.native_stream.start())
        result['teaching_events'] = teaching_events
        result['concept_query_events'] = query_events
        result['native_events'] = native_events
        result['native_query_events'] = recall_events
        result['native_statement_events'] = statement_events
        result['native_meaning_query_events'] = meaning_events
        result['native_feedback_events'] = feedback_events
        result['native_name_events'] = naming_events
        result['dialogue_events'] = dialogue_events
        self.interactions.poll()
        result["concept_inquiry"] = None
        if self.studies:
            item = self.studies[0]
            inquiry = self.concepts.choose_inquiry(item["options"])
            self.studies.pop(0)
            result["concept_inquiry"] = {**inquiry, "id": item["id"], "issued_at": item["issued_at"],
                                         "selected_at": self.clock, "external_result_required": True}
            self.inquiries[item["id"]] = copy.deepcopy(result["concept_inquiry"])
        return result

    def take_inquiry(self, number):
        if type(number) is not int:
            raise ValueError("Invalid inquiry delivery identifier.")
        return self.inquiries.pop(number, None)

    def submit_lesson(self, question, origin='person', ttl=300.):
        if self.teaching is None:
            raise ValueError("A conversational lesson requires a language coordinator.")
        return self.teaching.submit(question, origin, ttl)

    def take_lesson(self, number):
        if self.teaching is None:
            raise ValueError("This core has no conversational teaching queue.")
        return self.teaching.take(number)

    def close(self):
        try:
            if self.dialogues is not None:
                self.dialogues.close()
            self.native_stream.close()
            if self.teaching is not None:
                self.teaching.close()
            if self.concept_queries is not None:
                self.concept_queries.close()
            if self.native_queries is not None:
                self.native_queries.close()
            if self.native_statements is not None:
                self.native_statements.close()
            if self.native_meaning_queries is not None:
                self.native_meaning_queries.close()
            if self.native_feedbacks is not None:
                self.native_feedbacks.close()
            if self.native_namings is not None:
                self.native_namings.close()
        finally:
            try:
                self.native.moments.close()
            finally:
                if hasattr(self.agent, 'close'):
                    self.agent.close()

    def snapshot(self, moment_snapshot=None):
        from .runtime_snapshot import capture
        payload = {"format": 57 if moment_snapshot is None else 58, "agent": capture(self.agent), "concepts": self.concepts.snapshot(), "native": self.native.snapshot(moment_snapshot),
                'interactions': self.interactions.snapshot(),
                "native_stream": self.native_stream.snapshot(),
                'native_feedbacks': None if self.native_feedbacks is None else self.native_feedbacks.snapshot(),
                'native_namings': None if self.native_namings is None else self.native_namings.snapshot(),
                "native_queries": None if self.native_queries is None else self.native_queries.snapshot(),
                "native_statements": None if self.native_statements is None else self.native_statements.snapshot(),
                "native_meaning_queries": None if self.native_meaning_queries is None else self.native_meaning_queries.snapshot(),
                "studies": copy.deepcopy(self.studies), "inquiries": copy.deepcopy(self.inquiries),
                "next_study": self.next_study}
        if self.teaching is not None:
            payload.update(teaching=self.teaching.snapshot(), concept_queries=self.concept_queries.snapshot())
        return payload

    def submit_concept_question(self, question, ttl=300.):
        if self.concept_queries is None:
            raise ValueError("A conceptual question requires a language coordinator.")
        return self.concept_queries.submit(question, ttl)

    def submit_native_question(self, question, ttl=300.):
        if self.native_queries is None:
            raise ValueError('Native memory questions require a language coordinator.')
        return self.native_queries.submit(question, ttl)

    def take_native_answer(self, number):
        if self.native_queries is None:
            raise ValueError('This core has no native memory question queue.')
        return self.native_queries.take(number)

    def take_concept_answer(self, number):
        if self.concept_queries is None:
            raise ValueError("This core has no conceptual question queue.")
        return self.concept_queries.take(number)

    def perceive_native(self, packets, elapsed):
        from .contracts import interval
        from .native_sensor import NativeObservation
        interval(elapsed)
        if not isinstance(packets, (list, tuple)) or not 1 <= len(packets) <= 3 or any(not isinstance(item, NativeObservation) for item in packets):
            raise ValueError("Native perception requires typed encoder outputs.")
        for item in packets:
            item.validate()
            scalar(item.acquired_at, 0, self.clock + elapsed)
        if len({item.modality for item in packets}) != len(packets) or max(item.acquired_at for item in packets) - min(item.acquired_at for item in packets) > .025:
            raise ValueError("Native frame has repeated or unsynchronized modalities.")
        # One owner advances the existing continuous mind. The old classifier
        # never interprets the new encoder space as synthetic scene categories.
        result = self.tick(elapsed)
        result['native_perception'] = self.observe_native(packets)
        return result

    def observe_native(self, packets, source_context=None, *, regions=None):
        result = self.native.observe(packets, self.clock, source_context, regions=regions)
        errors = {**result.get('prediction_learning', {}).get('errors', {}),
                  **result.get('association_learning', {}).get('errors', {})}
        internal = getattr(self.mind, 'internal', None)
        if internal is not None and result['encoded']:
            if errors:
                internal.novelty = min(1., sum(errors.values()) / (2 * len(errors)))
            internal.advance(0., result['encoded'], False)
        return result

    def teach_native_name(self, item):
        return self.native.teach(item, self.clock)

    def associate_native(self, packet, target, contextual=False):
        return self.native.associate(packet, target, contextual)

    def configure_native_attention(self, mode):
        self.native.attention.configure(mode)

    def learn_native_attention(self, outcome, language=None):
        result = self.native.learn_attention(outcome, language)
        internal = getattr(self.mind, 'internal', None)
        if result['learned'] and internal is not None:
            internal.observe(outcome)
        return result

    def submit_native_feedback(self, message, action_id, origin='person', ttl=300.):
        if self.native_feedbacks is None:
            raise ValueError('Portuguese feedback requires a language coordinator.')
        return self.native_feedbacks.submit(message, action_id, origin, ttl)

    def submit_native_name(self, message, focus=None, moment=None, origin='person', ttl=300.):
        if self.native_namings is None:
            raise ValueError('Portuguese naming requires a language coordinator.')
        return self.native_namings.submit(message, focus, moment, origin, ttl)

    def take_native_name(self, number):
        if self.native_namings is None:
            raise ValueError('This core has no Portuguese naming queue.')
        return self.native_namings.take(number)

    def native_name_clarification(self, number):
        if self.native_namings is None:
            raise ValueError('This core has no Portuguese naming queue.')
        return self.native_namings.clarification(number)

    def reply_native_name(self, number, word, focus=None):
        if self.native_namings is None:
            raise ValueError('This core has no Portuguese naming queue.')
        return self.native_namings.reply(number, word, focus)

    def take_native_feedback(self, number):
        if self.native_feedbacks is None:
            raise ValueError('This core has no Portuguese feedback queue.')
        return self.native_feedbacks.take(number)

    def teach_native_interpretation(self, statement):
        return self.native.teach_interpretation(statement)

    def submit_native_statement(self, message, origin='person', ttl=300.):
        if self.native_statements is None:
            raise ValueError('A Portuguese native statement requires a language coordinator.')
        return self.native_statements.submit(message, origin, ttl)

    def take_native_statement(self, number):
        if self.native_statements is None:
            raise ValueError('This core has no native statement queue.')
        return self.native_statements.take(number)

    def submit_context_report(self, message, moment=None, correction=None, origin='person', ttl=300.):
        if self.native_statements is None:
            raise ValueError('A contextual report requires a language coordinator.')
        return self.native_statements.submit_context(message, moment, correction, origin, ttl)

    def submit_native_meaning_question(self, question, ttl=300.):
        if self.native_meaning_queries is None:
            raise ValueError('A meaning question requires a language coordinator.')
        return self.native_meaning_queries.submit(question, ttl)

    def submit_reference_question(self, question, binding, ttl=300.):
        if self.native_meaning_queries is None:
            raise ValueError('A referenced question requires a language coordinator.')
        return self.native_meaning_queries.submit_reference(question, binding, ttl)

    def take_native_meaning_answer(self, number):
        if self.native_meaning_queries is None:
            raise ValueError('This core has no meaning question queue.')
        return self.native_meaning_queries.take(number)


def save(path, agent):
    atomic_write(path, agent.snapshot())


def restore(payload, folder=None, worker_factory=None):
    from .continuous_experiment import restore_scheduler
    from .persistent_runtime import close_agent
    fields = {"format", "agent", "concepts", "studies", "inquiries", "next_study"}
    if isinstance(payload, dict) and payload.get('format') in (41, 42):
        fields.add('teaching')
    if isinstance(payload, dict) and payload.get('format') == 42:
        fields.add('concept_queries')
    if isinstance(payload, dict) and payload.get('format') in (43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        fields.add('native')
        if isinstance(payload.get('agent'), dict) and payload['agent'].get('format') in (30, 31, 39):
            fields.update(('teaching', 'concept_queries'))
    if isinstance(payload, dict) and payload.get('format') in (44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        fields.add('native_stream')
    if isinstance(payload, dict) and payload.get('format') in (47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        fields.add('native_queries')
    if isinstance(payload, dict) and payload.get('format') in (49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        fields.add('native_statements')
    if isinstance(payload, dict) and payload.get('format') in (51, 52, 53, 54, 55, 56, 57, 58):
        fields.add('native_meaning_queries')
    if isinstance(payload, dict) and payload.get('format') in (53, 54, 55, 56, 57, 58):
        fields.add('native_feedbacks')
    if isinstance(payload, dict) and payload.get('format') in (55, 56, 57, 58):
        fields.add('native_namings')
    if isinstance(payload, dict) and payload.get('format') in (57, 58):
        fields.add('interactions')
    if not isinstance(payload, dict) or set(payload) != fields or type(payload["format"]) is not int or payload["format"] not in (40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
        raise ValueError("Invalid conceptual mind checkpoint.")
    nested = payload["agent"]
    if not isinstance(nested, dict) or nested.get("format") not in (29, 30, 31, 35, 39):
        raise ValueError("Invalid conceptual mind base checkpoint.")
    agent, mind, _ = restore_scheduler(nested, folder, worker_factory)
    result = None
    try:
        result = ConceptualMind(agent)
        if payload['format'] in (43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58):
            from .native_grounding import restore as restore_native
            result.native.moments.close()
            result.native = restore_native(payload['native'], agent.clock)
            from .native_stream import NativeStream, restore as restore_native_stream
            result.native_stream = (restore_native_stream(payload['native_stream'], result) if payload['format'] in (44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58)
                                    else NativeStream(result))
        if result.native_queries is not None:
            from .native_query import NativeQueryLane, restore as restore_native_queries
            result.native_queries = (restore_native_queries(payload['native_queries'], agent, result.native)
                                     if payload['format'] in (47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58) else NativeQueryLane(agent, result.native))
        elif payload.get('native_queries') is not None:
            raise ValueError('Native memory questions require a language core.')
        if result.native_statements is not None:
            from .native_statement import NativeStatementLane, restore as restore_native_statements
            result.native_statements = (restore_native_statements(payload['native_statements'], agent, result.native)
                                       if payload['format'] in (49, 50, 51, 52, 53, 54, 55, 56, 57, 58) else NativeStatementLane(agent, result.native))
        elif payload.get('native_statements') is not None:
            raise ValueError('Native statements require a language core.')
        if result.native_meaning_queries is not None:
            from .native_meaning_query import NativeMeaningQueryLane, restore as restore_meaning_queries
            result.native_meaning_queries = (restore_meaning_queries(payload['native_meaning_queries'], agent, result.native)
                if payload['format'] in (51, 52, 53, 54, 55, 56, 57, 58) else NativeMeaningQueryLane(agent, result.native))
        elif payload.get('native_meaning_queries') is not None:
            raise ValueError('Meaning questions require a language core.')
        if result.native_feedbacks is not None:
            from .native_feedback import FeedbackLane, restore as restore_feedbacks
            result.native_feedbacks = (restore_feedbacks(payload['native_feedbacks'], agent, result)
                if payload['format'] in (53, 54, 55, 56, 57, 58) else FeedbackLane(agent, result))
        elif payload.get('native_feedbacks') is not None:
            raise ValueError('Portuguese feedback requires a language core.')
        if result.native_namings is not None:
            from .native_name import NativeNameLane, restore as restore_namings
            result.native_namings = (restore_namings(payload['native_namings'], agent, result.native)
                if payload['format'] in (55, 56, 57, 58) else NativeNameLane(agent, result.native))
        elif payload.get('native_namings') is not None:
            raise ValueError('Portuguese naming requires a language core.')
        if payload['format'] in (57, 58):
            from .interaction_session import restore as restore_interactions
            result.interactions = restore_interactions(payload['interactions'], result)
        result.concepts = restore_concepts(payload["concepts"], agent.clock)
        if result.teaching is not None:
            result.teaching.concepts = result.concepts
            result.concept_queries.concepts = result.concepts
        if 'teaching' in payload:
            from .concept_teaching import restore as restore_teaching
            if result.teaching is None:
                raise ValueError("Teaching checkpoint requires a language core.")
            result.teaching = restore_teaching(payload['teaching'], agent, result.concepts)
        if 'concept_queries' in payload:
            from .concept_query import restore as restore_queries
            result.concept_queries = restore_queries(payload['concept_queries'], agent, result.concepts)
        studies, next_study = payload["studies"], payload["next_study"]
        inquiries = payload["inquiries"]
        if not isinstance(studies, list) or not isinstance(inquiries, dict) or len(studies) + len(inquiries) > 8 or type(next_study) is not int or not 1 <= next_study <= 1000001:
            raise ValueError("Invalid saved conceptual inquiry queue.")
        ids = []
        for item in studies:
            if not isinstance(item, dict) or set(item) != {"id", "options", "issued_at"} or type(item["id"]) is not int or not 1 <= item["id"] < next_study:
                raise ValueError("Invalid saved conceptual inquiry.")
            scalar(item["issued_at"], 0, agent.clock)
            result.concepts.choose_inquiry(item["options"])
            ids.append(item["id"])
        if ids != sorted(set(ids)):
            raise ValueError("Duplicate or reordered conceptual inquiries.")
        for number, item in inquiries.items():
            expected = {"concept", "input", "cost", "uncertainty", "score", "reason", "general_curiosity", "id", "issued_at", "selected_at", "external_result_required"}
            if type(number) is not int or number in ids or not 1 <= number < next_study or not isinstance(item, dict) or set(item) != expected or type(item["id"]) is not int or item["id"] != number or item["reason"] != "weight_covariance_and_cost" or item["general_curiosity"] is not False or item["external_result_required"] is not True:
                raise ValueError("Invalid saved conceptual inquiry delivery.")
            result.concepts.choose_inquiry([{key: item[key] for key in ("concept", "input", "cost")}])
            scalar(item["issued_at"], 0, agent.clock)
            scalar(item["selected_at"], item["issued_at"], agent.clock)
            scalar(item["uncertainty"], 0, 1000.)
            scalar(item["score"], 0, 1000.)
        result.studies, result.next_study = copy.deepcopy(studies), next_study
        result.inquiries = copy.deepcopy(inquiries)
        return result
    except BaseException:
        close_agent(agent if result is None else result, mind)
        raise
