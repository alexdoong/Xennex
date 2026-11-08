"""Opt-in continuous Alice runtime with durable state and no live sensors.

The CLI runs until Ctrl+C/stop.request, or for an explicit finite duration. It
does not install an autostart service or dispatch motor outputs to the OS.
"""
from __future__ import annotations

import argparse
import math
import pickle
import time
from collections import deque
from pathlib import Path
from uuid import uuid4

import torch

from .continuous_experiment import load_scheduler
from .language_process import LanguageProcess
from .process_metrics import memory_usage, quantiles
from .runtime_store import RuntimeStore, atomic_json

MAX_GAP = 7 * 24 * 3600


def summary(values):
    return quantiles(list(values)) if values else {"p50": None, "p95": None, "p99": None}


def restore_runtime(store, checkpoint, folder, factory):
    if store.manifest is None:
        if checkpoint is None:
            raise ValueError("A new runtime requires an initial checkpoint.")
        agent, mind, serializer = load_scheduler(checkpoint, folder, factory)
        return agent, mind, {"resumed": False, "source": str(checkpoint.resolve()), "offline_seconds": 0., "rollback": False}
    errors = []
    for path, record in store.candidates():
        agent = mind = None
        try:
            agent, mind, serializer = load_scheduler(path, folder, factory)
            if agent.clock != record["clock"]:
                raise ValueError("Runtime checkpoint clock disagrees with its commit record.")
            delta = time.time() - record["captured_wall"]
            if delta > MAX_GAP:
                raise ValueError("Offline interval exceeds the current seven-day temporal protocol.")
            store.use_recovered(record)
            return agent, mind, {"resumed": True, "source": path.name, "offline_seconds": max(0., delta),
                                 "rollback": delta < 0, "recovery_errors": store.recovery_errors + errors}
        except (OSError, RuntimeError, ValueError, pickle.UnpicklingError) as error:
            if agent is not None:
                close_agent(agent, mind)
            errors.append({"file": record["file"], "error": type(error).__name__ + ": " + str(error)[:512]})
    raise ValueError("Runtime could not restore a supported intact generation: " + str(errors)[:1024])


def close_agent(agent, mind):
    try:
        if hasattr(agent, "close"):
            agent.close()
    finally:
        if hasattr(mind.actor.session.memory, "close"):
            mind.actor.session.memory.close()


def advance(agent, elapsed, gap_threshold=2.):
    if not math.isfinite(elapsed) or not 0 <= elapsed <= MAX_GAP:
        raise ValueError("Invalid persistent runtime elapsed interval.")
    if elapsed > gap_threshold:
        agent.unobserved_gap(elapsed)
        return agent.tick(0.), True
    return agent.tick(elapsed), False


def jobs(agent):
    return [{"id": value["id"], "mode": value["mode"], "status": value["status"], "error": value["error"],
             "proposal": value["proposal"]} for value in getattr(agent, "jobs", {}).values()]


def teaching_jobs(agent):
    lane = getattr(agent, 'teaching', None)
    return [] if lane is None else [{'id': job['id'], 'status': job['status'], 'error': job['error'],
                                    'learning': job['learning']} for job in lane.jobs.values()]


def concept_query_jobs(agent):
    lane = getattr(agent, 'concept_queries', None)
    return [] if lane is None else [{'id': job['id'], 'status': job['status'], 'error': job['error'],
                                    'evidence': job['evidence'], 'proposal': job['proposal'],
                                    'numeric_text_verified': job['status'] == 'completed' and lane.current(job['evidence']),
                                    'free_text_semantics_verified': False, 'revisions': job['revisions']}
                                   for job in lane.jobs.values()]


def native_state(agent):
    native = getattr(agent, 'native', None)
    if native is None:
        return None
    from .native_sensor import REPRESENTATION
    from .recall_feedback import available as available_recall_feedback
    return {'representation': REPRESENTATION, 'clock': native.clock, 'observations': native.observations,
            'implicit_recall': native.implicit_recall,
            'recall_preference_updates': 0 if native.recall_preference is None else int(native.recall_preference.bank.writes),
            'recall_feedback_actions': available_recall_feedback(agent),
            'names': native.names.copy(), 'lessons': len(native.sources), 'working_norm': float(native.working.norm()),
            'moments': len(native.moments.traces), 'moment_cache': len(native.moments.cache),
            'lifetime_moments': native.moments.next_id,
            'visual_region_moments': len(native.moments.regions),
            'last_visual_detection': last_visual_detection(agent),
            'last_sound_association': last_sound_association(agent),
            'last_pronunciation': last_pronunciation(agent),
            'pronunciation_examples': len(native.moments.pronunciations),
            'forgotten_moments': native.moments.next_id - len(native.moments.traces),
            'pre_archive_observations': native.moments.pre_archive_observations,
            'interpretation_versions': len(native.interpretations.records),
            'prediction_frames': native.dynamics.frames, 'prediction_pairs': native.dynamics.pairs,
            'prediction_updates': {name: int(bank.writes) for name, bank in native.dynamics.banks.items()},
            'prediction_errors': native.dynamics.last_error.copy(),
            'received_observations': native.received_observations,
            'unattended_observations': native.received_observations - native.observations,
            'attention_mode': native.attention.mode,
            'attention_feedbacks': len(native.attention.sources),
            'attention_actions': native_attention_actions(agent),
            'file_inbox_enabled': getattr(agent, 'native_stream', None) is not None and agent.native_stream.factory is not None,
            'live_sensor_inbox': False}


def last_visual_detection(agent):
    stream = getattr(agent, 'native_stream', None)
    if stream is None:
        return None
    frames = [job for job in (*stream.jobs.values(), *stream.deliveries)
              if job['result'] is not None and 'region_status' in job['result']]
    if not frames:
        return None
    result = max(frames, key=lambda job: job['source_sequence'])['result']
    return {'status': result['region_status'], 'count': result['region_count']}


def last_sound_association(agent):
    stream = getattr(agent, 'native_stream', None)
    if stream is None:
        return None
    latest = max((job for job in (*stream.jobs.values(), *stream.deliveries)
                  if job['result'] is not None and (job['result'].get('attention') or {}).get('modalities') == ['audio']),
                 key=lambda job: job['source_sequence'], default=None)
    evidence = None if latest is None else latest['result'].get('audio_association')
    return None if evidence is None else {'name': evidence['name'], 'count': len(evidence['sources'])}


def last_pronunciation(agent):
    stream = getattr(agent, 'native_stream', None)
    if stream is None:
        return None
    latest = max((job for job in (*stream.jobs.values(), *stream.deliveries)
                  if job['result'] is not None and 'pronunciation' in job['result']),
                 key=lambda job: job['source_sequence'], default=None)
    if latest is None:
        return None
    result = latest['result']['pronunciation']
    return {'status': result['status'], 'word': result.get('word'), 'source_sequence': latest['source_sequence']}


def native_attention_actions(agent):
    queued = set() if getattr(agent, 'native_feedbacks', None) is None else {job['action_id'] for job in agent.native_feedbacks.jobs.values()}
    stream = getattr(agent, 'native_stream', None)
    frames = [] if stream is None else [*stream.jobs.values(), *stream.deliveries]
    result = []
    for number, choice in sorted(agent.native.attention.pending.items()):
        if number in queued or agent.clock > choice['issued'] + 60:
            continue
        frame = next((job for job in frames if job['result'] is not None and (job['result'].get('attention') or {}).get('id') == number), None)
        result.append({'id': number, 'action': choice['action'], 'age_seconds': max(0., agent.clock - choice['issued']),
                       'frame': None if frame is None else {'stream_id': stream.stream_id, 'sequence': frame['source_sequence']}})
    return result


def native_query_jobs(agent, lane_name='native_queries'):
    lane = getattr(agent, lane_name, None)
    return [] if lane is None else [{'id': job['id'], 'status': job['status'], 'error': job['error'],
            'evidence': job['evidence'], 'proposal': job['proposal'], 'revisions': job['revisions'],
            'factual_text_verified': job['status'] == 'completed' and lane.current(job['evidence']),
            'expression_policy': 'bounded_grounded_phrases'} for job in lane.jobs.values()]


def native_statement_jobs(agent, lane_name='native_statements'):
    lane = getattr(agent, lane_name, None)
    if lane is None:
        return []
    entries = [{'id': job['id'], 'status': job['status'], 'error': job['error'], 'learning': job['learning']} for job in lane.jobs.values()]
    if lane_name == 'native_namings':
        for entry in entries:
            entry['clarification'] = lane.clarification(entry['id'])
    return entries


def native_jobs(agent):
    stream = getattr(agent, 'native_stream', None)
    if stream is None:
        return None
    return {'source_sequence': stream.last_source_sequence,
            'jobs': [dict(job) for job in stream.jobs.values()], 'recent_deliveries': stream.deliveries.copy()}


def configure_language(agent, endpoint=None, model=None):
    if endpoint is None and model is None:
        return
    from .conceptual_mind import ConceptualMind
    from .language_coordinator import LanguageCoordinator
    from .language import LocalLanguage
    coordinator = agent.agent if isinstance(agent, ConceptualMind) else agent
    if not isinstance(coordinator, LanguageCoordinator):
        raise ValueError("Language selection requires a language-coordinator checkpoint.")
    endpoint = coordinator.endpoint if endpoint is None else endpoint
    model = coordinator.model if model is None else model
    LocalLanguage(endpoint, model)  # Syntax/loopback validation; no network or load.
    if endpoint == coordinator.endpoint and model == coordinator.model:
        return
    lane = getattr(agent, 'teaching', None)
    queries = getattr(agent, 'concept_queries', None)
    native_queries = getattr(agent, 'native_queries', None)
    native_statements = getattr(agent, 'native_statements', None)
    feedbacks = getattr(agent, 'native_feedbacks', None)
    namings = getattr(agent, 'native_namings', None)
    meaning_queries = getattr(agent, 'native_meaning_queries', None)
    dialogues = getattr(agent, 'dialogues', None)
    if coordinator.closed or coordinator.jobs or coordinator.worker is not None or coordinator.external_worker_owner is not None or (lane is not None and lane.jobs) or (queries is not None and queries.jobs) or (native_queries is not None and native_queries.jobs) or (native_statements is not None and native_statements.jobs) or (meaning_queries is not None and meaning_queries.jobs) or (feedbacks is not None and feedbacks.jobs) or (namings is not None and namings.jobs) or (dialogues is not None and dialogues.jobs):
        raise ValueError("Language selection requires empty queues and no active worker.")
    coordinator.endpoint, coordinator.model = endpoint, model


def configure_dialogue(agent, model=None):
    if model is None:
        return
    lane = getattr(agent, 'dialogues', None)
    if lane is None:
        raise ValueError('Dialogue selection requires a conceptual language owner.')
    lane.configure(None if model == '' else model)


def run(root, checkpoint=None, *, seconds=None, period=.1, save_every=5., language_backend="installed", question=None,
        question_mode="expectation", lesson=None, language_endpoint=None, language_model=None, dialogue_model=None,
        native_inbox=None, native_models=None, native_interpreter=None, native_backend='installed', native_ram_fraction=.75, native_mirage=None,
        native_statement=None, native_attention=None, native_feedback=None, attention_feedback=None, native_name=None, native_name_reply=None, interaction_inbox=None, native_implicit_recall=None):
    if native_implicit_recall is not None and type(native_implicit_recall) is not bool:
        raise ValueError('Invalid implicit native recall mode.')
    for value, lower, upper in ((period, .01, 1.), (save_every, 1., 3600.)):
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not lower <= value <= upper:
            raise ValueError("Invalid runtime period/persistence interval.")
    if seconds is not None and (isinstance(seconds, bool) or not isinstance(seconds, (float, int)) or not math.isfinite(seconds) or not .1 <= seconds <= 3600.):
        raise ValueError("Finite runtime duration must be between 0.1 and 3600 seconds.")
    if language_backend not in ("installed", "fixture") or question_mode not in ("expectation", "recall", "concept", "native", "meaning"):
        raise ValueError("Invalid runtime language backend/question mode.")
    if native_attention is not None and native_attention not in ('full', 'learned', 'quiet'):
        raise ValueError('Invalid runtime native attention mode.')
    if native_feedback is not None and (not callable(native_feedback) or native_inbox is None):
        raise ValueError('Native attention feedback requires a local observer and file inbox.')
    if native_backend not in ('installed', 'fixture') or isinstance(native_ram_fraction, bool) or not isinstance(native_ram_fraction, (int, float)) or not .5 <= native_ram_fraction <= .9:
        raise ValueError("Invalid native inbox backend/budget.")
    if native_ram_fraction > .75 and seconds is None:
        raise ValueError("Native budget override above 75% requires a finite experimental duration.")
    if native_mirage is not None and (native_inbox is None or native_backend != 'installed' or not Path(native_mirage).is_dir()):
        raise ValueError('Local Mirage requires an installed file inbox and detector directory.')
    torch.set_num_threads(1)
    with RuntimeStore(root) as store:
        folder = store.root / ("workers-" + uuid4().hex)
        folder.mkdir()
        workers = []
        fixture = folder / "fixture.json"
        if language_backend == "fixture":
            atomic_json(fixture, {"delay": .2})

        def factory(operation):
            options = ("scripts.tests.alice_fake_language_worker", {"ALICE_FAKE_LANGUAGE_CONFIG": str(fixture)}) if language_backend == "fixture" else ("scripts.alice_memory.language_worker", None)
            worker = LanguageProcess(operation, folder, 120., options[0], options[1])
            workers.append(worker)
            # Retain only live handles; completed jobs remain in the core checkpoint.
            workers[:] = [item for item in workers if item.process.poll() is None]
            return worker

        agent = mind = None
        observations = initial_episodes = None
        captures, iterations, lag = deque(maxlen=1024), deque(maxlen=1024), deque(maxlen=1024)
        persist_events = deque(maxlen=32)
        inbox_errors = deque(maxlen=16)
        native_workers = []
        inbox = inbox_lease = None
        interactions = interaction_lease = None
        captured_interactions = previous_interactions = previous_interaction_commit = None
        captured_native_jobs = []
        previous_native_jobs = set()
        previous_native_commit = None

        def native_commit(event, numbers):
            nonlocal previous_native_jobs, previous_native_commit
            if event is None or event['status'] != 'committed' or inbox is None:
                return
            try:
                confirmed = previous_native_jobs.intersection(numbers)
                agent.native_stream.committed(confirmed, event['record'], previous_native_commit)
            except (OSError, RuntimeError, ValueError) as error:
                inbox_errors.append({'phase': 'ack', 'error': str(error)[:1024]})
            previous_native_jobs, previous_native_commit = set(numbers), event['record']
        def interaction_commit(event, captured):
            nonlocal previous_interactions, previous_interaction_commit
            if event is None or event['status'] != 'committed' or interactions is None or captured is None:
                return
            try:
                agent.interactions.committed(captured, previous_interactions, interactions,
                                             event['record'], previous_interaction_commit)
            except (OSError, ValueError) as error:
                inbox_errors.append({'phase': 'interaction_ack', 'error': str(error)[:1024]})
            previous_interactions, previous_interaction_commit = captured, event['record']

        started = time.perf_counter()
        cpu_started = time.process_time()
        report = {"phase": "loading", "language_backend": language_backend, "live_sensors": False,
                  "run_id": uuid4().hex,
                  "language_quality_evaluated": False, "autostart_installed": False, "ticks": 0,
                  "writer_commits": 0, "checkpoint_capture_ms": {}, "unobserved_runtime_gaps": 0}
        atomic_json(store.root / "status.json", report)
        try:
            agent, mind, recovery = restore_runtime(store, checkpoint, folder, factory)
            report["recovery"] = recovery
            if recovery["offline_seconds"]:
                agent.unobserved_gap(recovery["offline_seconds"])
            configure_language(agent, language_endpoint, language_model)
            if dialogue_model is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
            configure_dialogue(agent, dialogue_model)
            if native_implicit_recall is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.native.configure_implicit_recall(native_implicit_recall)
            if native_attention is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.configure_native_attention(native_attention)
            if native_inbox is not None:
                from .conceptual_mind import ConceptualMind
                from .native_inbox import NativeInbox
                from .native_process import NativeProcess
                from .runtime_store import RuntimeLease
                import sys
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                inbox = NativeInbox(native_inbox)
                inbox_lease = RuntimeLease(inbox.root)
                models = inbox.root if native_models is None else Path(native_models)
                interpreter = Path(sys.executable) if native_interpreter is None else Path(native_interpreter)
                if native_backend == 'installed' and (native_models is None or native_interpreter is None):
                    raise ValueError("Installed native inbox requires pinned models and the isolated interpreter.")
                native_config = folder / 'native-fixture.json'
                if native_backend == 'fixture':
                    atomic_json(native_config, {'delay': .3})

                def native_factory(selected):
                    options = ('scripts.tests.alice_fake_native_worker', {'ALICE_FAKE_NATIVE_CONFIG': str(native_config)}) if native_backend == 'fixture' else ('scripts.alice_memory.native_stream_worker', None)
                    worker = NativeProcess(selected, inbox, folder / 'native', models, interpreter,
                                           native_ram_fraction, options[0], options[1], mirage_folder=native_mirage)
                    native_workers.append(worker)
                    native_workers[:] = [item for item in native_workers if item.process.poll() is None]
                    return worker

                agent.native_stream.configure(inbox, native_factory, native_feedback)
            if interaction_inbox is not None:
                from .conceptual_mind import ConceptualMind
                from .interaction_inbox import InteractionInbox
                from .runtime_store import RuntimeLease
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                interactions = InteractionInbox(interaction_inbox)
                interaction_lease = RuntimeLease(interactions.root / 'consumer')
                agent.interactions.configure(interactions)
                if store.manifest is not None:
                    previous_interactions = agent.interactions.snapshot()
                    previous_interaction_commit = store.manifest['current']
            if lesson is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.submit_lesson(lesson)
            if question is not None:
                if not hasattr(agent, "submit"):
                    raise ValueError("A runtime question requires a language-coordinator checkpoint.")
                if question_mode in ('native', 'meaning'):
                    from .conceptual_mind import ConceptualMind
                    if not isinstance(agent, ConceptualMind):
                        agent = ConceptualMind(agent)
                    if question_mode == 'meaning':
                        agent.submit_native_meaning_question(question)
                    else:
                        agent.submit_native_question(question)
                elif question_mode == 'concept':
                    from .conceptual_mind import ConceptualMind
                    if not isinstance(agent, ConceptualMind):
                        agent = ConceptualMind(agent)
                    agent.submit_concept_question(question)
                elif question_mode == "expectation":
                    agent.submit_expectation(question)
                else:
                    agent.submit(question)
            if native_statement is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.submit_native_statement(native_statement)
            if native_name is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(native_name, dict) or set(native_name) != {'message', 'focus', 'moment'}:
                    raise ValueError('Invalid Portuguese native-name request.')
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.submit_native_name(native_name['message'], native_name['focus'], native_name['moment'])
            if native_name_reply is not None:
                if not isinstance(native_name_reply, dict) or set(native_name_reply) != {'id', 'word', 'focus'} or not hasattr(agent, 'reply_native_name'):
                    raise ValueError('Invalid or unavailable native-name clarification reply.')
                agent.reply_native_name(native_name_reply['id'], native_name_reply['word'], native_name_reply['focus'])
            if attention_feedback is not None:
                from .conceptual_mind import ConceptualMind
                if not isinstance(attention_feedback, dict) or set(attention_feedback) != {'message', 'action_id'}:
                    raise ValueError('Portuguese feedback needs a message and selected action.')
                if not isinstance(agent, ConceptualMind):
                    agent = ConceptualMind(agent)
                agent.submit_native_feedback(attention_feedback['message'], attention_feedback['action_id'])
            observations = getattr(getattr(agent, "temporal", None), "observations", None)
            initial_episodes = len(mind.actor.session.memory.blocks)
            started = previous = time.perf_counter()
            cpu_started = time.process_time()
            next_save = next_status = started
            deadline = started + period
            stopped = "duration"
            report.update(phase="running", initial_clock=agent.clock, initial_episodes=initial_episodes)
            while seconds is None or time.perf_counter() - started < seconds:
                if (store.root / "stop.request").is_file():
                    stopped = "stop_request"
                    break
                time.sleep(max(0., deadline - time.perf_counter()))
                now = time.perf_counter()
                elapsed = now - previous
                previous = now
                lag.append(max(0., now - deadline) * 1000)
                deadline = max(deadline + period, now + period)
                result, gap = advance(agent, elapsed, max(2., period * 10))
                report["ticks"] += 1
                report["unobserved_runtime_gaps"] += int(gap)
                persisted = store.poll()
                if persisted is not None:
                    persist_events.append(persisted)
                    native_commit(persisted, captured_native_jobs)
                    interaction_commit(persisted, captured_interactions)
                    captured_interactions = None
                    captured_native_jobs = []
                if inbox is not None:
                    try:
                        for frame in inbox.available(agent.native_stream.last_source_sequence):
                            if len(agent.native_stream.jobs) >= 4:
                                break
                            try:
                                agent.native_stream.ingest(frame, inbox.read(frame), time.time())
                            except (OSError, RuntimeError, ValueError) as error:
                                inbox_errors.append({'phase': 'ingest', 'frame': frame, 'error': str(error)[:1024]})
                    except (OSError, RuntimeError, ValueError) as error:
                        inbox_errors.append({'phase': 'scan', 'error': str(error)[:1024]})
                if interactions is not None:
                    try:
                        for filename in interactions.available():
                            try:
                                request = interactions.request(filename)
                                accepted = agent.interactions.ingest(request)
                                if not accepted:
                                    if request['sequence'] <= agent.interactions.last_sequence:
                                        # Retired/replayed files do not reapply an
                                        # input or block newer queued interactions.
                                        continue
                                    break
                            except (OSError, ValueError) as error:
                                inbox_errors.append({'phase': 'interaction_ingest', 'file': filename, 'error': str(error)[:1024]})
                        agent.interactions.poll()
                    except (OSError, ValueError) as error:
                        inbox_errors.append({'phase': 'interaction_scan', 'error': str(error)[:1024]})
                if now >= next_save and store.future is None:
                    capture_started = time.perf_counter()
                    payload = store.capture(agent)
                    captured_interactions = None if interactions is None else agent.interactions.snapshot()
                    captures.append((time.perf_counter() - capture_started) * 1000)
                    store.submit(payload, agent.clock)
                    captured_native_jobs = [] if inbox is None else [job['id'] for job in payload['native_stream']['jobs'] if job['status'] in ('completed', 'ignored', 'failed')]
                    next_save = now + save_every
                iterations.append((time.perf_counter() - now) * 1000)
                if now >= next_status:
                    report.update(clock=agent.clock, writer_commits=store.committed, save_error=store.last_error,
                                  writer_busy=store.future is not None, jobs=jobs(agent), resources=memory_usage(),
                                  concept_inquiries=list(getattr(agent, "inquiries", {}).values()), teaching_jobs=teaching_jobs(agent),
                                  concept_query_jobs=concept_query_jobs(agent), native_state=native_state(agent), native_query_jobs=native_query_jobs(agent), native_meaning_query_jobs=native_query_jobs(agent, 'native_meaning_queries'), native_statement_jobs=native_statement_jobs(agent), native_feedback_jobs=native_statement_jobs(agent, 'native_feedbacks'), native_name_jobs=native_statement_jobs(agent, 'native_namings'),
                                  interaction_state=None if interactions is None else agent.interactions.snapshot(),
                                  native_stream=native_jobs(agent), native_inbox_errors=list(inbox_errors))
                    atomic_json(store.root / "status.json", report)
                    next_status = now + 1.
            report["stop_reason"] = stopped
        except KeyboardInterrupt:
            report["stop_reason"] = "interrupt"
        except Exception as error:
            report.update(phase="failed", error=type(error).__name__ + ": " + str(error)[:1024])
            raise
        finally:
            if agent is not None:
                try:
                    report["phase"] = "stopping" if report["phase"] != "failed" else "failed"
                    persisted = store.finish()
                    if persisted is not None:
                        persist_events.append(persisted)
                        native_commit(persisted, captured_native_jobs)
                        interaction_commit(persisted, captured_interactions)
                    for final_attempt in range(2):
                        if final_attempt:
                            native_pending = inbox is not None and any(job['status'] in ('completed', 'ignored', 'failed') for job in agent.native_stream.jobs.values())
                            interaction_pending = interactions is not None and any(item['status'] in ('completed', 'failed', 'awaiting_reply') and item['published'] < item['revision'] for item in agent.interactions.records.values())
                            if not native_pending and not interaction_pending:
                                break
                        # A result can arrive after the last scheduled capture.
                        # Persist it twice before acknowledging at shutdown;
                        # never advance cognition or launch pending workers here.
                        capture_started = time.perf_counter()
                        payload = store.capture(agent)
                        captured_interactions = None if interactions is None else agent.interactions.snapshot()
                        captures.append((time.perf_counter() - capture_started) * 1000)
                        store.submit(payload, agent.clock)
                        persisted = store.finish()
                        persist_events.append(persisted)
                        interaction_commit(persisted, captured_interactions)
                        if persisted['status'] != 'committed':
                            break
                        if inbox is not None:
                            numbers = [job['id'] for job in payload['native_stream']['jobs'] if job['status'] in ('completed', 'ignored', 'failed')]
                            native_commit(persisted, numbers)
                    wall = time.perf_counter() - started
                    report.update(clock=agent.clock, writer_commits=store.committed, save_error=store.last_error,
                                  writer_busy=False, jobs=jobs(agent), episodes=len(mind.actor.session.memory.blocks),
                                  episode_count_unchanged=len(mind.actor.session.memory.blocks) == initial_episodes,
                                  observation_count_unchanged=getattr(getattr(agent, "temporal", None), "observations", None) == observations,
                                  checkpoint_capture_ms=summary(captures), iteration_ms=summary(iterations),
                                  scheduler_lag_ms=summary(lag), persistence_events=list(persist_events),
                                  wall_seconds=wall, cpu_seconds=time.process_time() - cpu_started, resources=memory_usage(),
                                  concept_inquiries=list(getattr(agent, "inquiries", {}).values()), teaching_jobs=teaching_jobs(agent),
                                  concept_query_jobs=concept_query_jobs(agent), native_state=native_state(agent), native_query_jobs=native_query_jobs(agent), native_meaning_query_jobs=native_query_jobs(agent, 'native_meaning_queries'), native_statement_jobs=native_statement_jobs(agent), native_feedback_jobs=native_statement_jobs(agent, 'native_feedbacks'), native_name_jobs=native_statement_jobs(agent, 'native_namings'),
                                  interaction_state=None if interactions is None else agent.interactions.snapshot(),
                                  native_stream=native_jobs(agent), native_inbox_errors=list(inbox_errors))
                    if report["phase"] != "failed":
                        report["phase"] = "stopped" if store.last_error is None else "failed"
                finally:
                    try:
                        close_agent(agent, mind)
                    finally:
                        if interaction_lease is not None:
                            interaction_lease.close()
                            interaction_lease = None
                        if inbox_lease is not None:
                            inbox_lease.close()
                            inbox_lease = None
                    report['native_stream'] = native_jobs(agent)
            if interaction_lease is not None:
                interaction_lease.close()
            if inbox_lease is not None:
                inbox_lease.close()
            report["workers_terminal"] = all(worker.process.poll() is not None for worker in workers)
            report['native_workers_terminal'] = all(worker.process.poll() is not None for worker in native_workers)
            atomic_json(store.root / ("run-" + report["run_id"] + ".json"), report)
            atomic_json(store.root / "status.json", report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--seconds", type=float)
    parser.add_argument("--period", type=float, default=.1)
    parser.add_argument("--save-every", type=float, default=5.)
    parser.add_argument("--language-backend", choices=("installed", "fixture"), default="installed")
    parser.add_argument("--question-file", type=Path)
    parser.add_argument("--lesson-file", type=Path)
    parser.add_argument('--native-statement-file', type=Path)
    parser.add_argument("--endpoint", dest='language_endpoint')
    parser.add_argument("--model", dest='language_model')
    parser.add_argument('--dialogue-model', help='Installed expression model; empty uses the parser model, omitted preserves checkpoint selection.')
    parser.add_argument('--native-implicit-recall', action=argparse.BooleanOptionalAction, default=None,
                        help='Experimental nonverbal reactivation after each acquired percept; omitted preserves checkpoint mode.')
    parser.add_argument("--question-mode", choices=("expectation", "recall", "concept", "native", "meaning"), default="expectation")
    parser.add_argument('--interaction-inbox', type=Path)
    parser.add_argument('--native-inbox', type=Path)
    parser.add_argument('--native-models', type=Path)
    parser.add_argument('--native-mirage', type=Path, help='Optional local Mirage assets for automatic image regions.')
    parser.add_argument('--native-interpreter', type=Path)
    parser.add_argument('--native-backend', choices=('installed', 'fixture'), default='installed')
    parser.add_argument('--native-ram-fraction', type=float, default=.75)
    parser.add_argument('--native-attention', choices=('full', 'learned', 'quiet'))
    parser.add_argument('--native-name-file', type=Path)
    parser.add_argument('--native-name-reply-file', type=Path)
    parser.add_argument('--native-name-reply-id', type=int)
    parser.add_argument('--native-name-reply-focus', choices=('image', 'audio', 'text'))
    parser.add_argument('--native-name-focus', choices=('image', 'audio', 'text'))
    parser.add_argument('--native-name-moment', type=int)
    parser.add_argument('--attention-feedback-file', type=Path)
    parser.add_argument('--attention-feedback-action', type=int)
    args = parser.parse_args()
    question = None
    if args.question_file:
        from .expectation_language import question_from_file
        question = question_from_file(args.question_file)
    lesson = None
    if args.lesson_file:
        from .expectation_language import question_from_file
        lesson = question_from_file(args.lesson_file)
    native_statement = None
    native_name = None
    native_name_reply = None
    attention_feedback = None
    if (args.native_name_reply_file is None) != (args.native_name_reply_id is None):
        raise ValueError('Naming reply file and context id must be supplied together.')
    if args.native_name_reply_file:
        if args.native_name_reply_file.stat().st_size > 256:
            raise ValueError('Naming word reply exceeds its file budget.')
        native_name_reply = {'id': args.native_name_reply_id, 'word': args.native_name_reply_file.read_text(encoding='utf-8').strip(), 'focus': args.native_name_reply_focus}
    elif args.native_name_reply_focus is not None:
        raise ValueError('Naming reply focus requires a word reply.')
    if args.native_name_file:
        if args.native_name_file.stat().st_size > 8192:
            raise ValueError('Native naming file exceeds its budget.')
        native_name = {'message': args.native_name_file.read_text(encoding='utf-8'), 'focus': args.native_name_focus, 'moment': args.native_name_moment}
    elif args.native_name_focus is not None or args.native_name_moment is not None:
        raise ValueError('Native naming focus/moment requires a teaching file.')
    if (args.attention_feedback_file is None) != (args.attention_feedback_action is None):
        raise ValueError('Feedback file and selected action must be provided together.')
    if args.attention_feedback_file:
        if args.attention_feedback_file.stat().st_size > 8192:
            raise ValueError('Feedback file exceeds its budget.')
        attention_feedback = {'message': args.attention_feedback_file.read_text(encoding='utf-8'), 'action_id': args.attention_feedback_action}
    if args.native_statement_file:
        from .expectation_language import question_from_file
        native_statement = question_from_file(args.native_statement_file)
    report = run(args.store, args.checkpoint, seconds=args.seconds, period=args.period, save_every=args.save_every,
                 language_backend=args.language_backend, question=question, question_mode=args.question_mode, lesson=lesson,
                 language_endpoint=args.language_endpoint, language_model=args.language_model, dialogue_model=args.dialogue_model,
                 native_inbox=args.native_inbox, native_models=args.native_models, native_interpreter=args.native_interpreter,
                 native_backend=args.native_backend, native_ram_fraction=args.native_ram_fraction, native_mirage=args.native_mirage,
                 native_statement=native_statement, native_attention=args.native_attention, attention_feedback=attention_feedback, native_name=native_name, native_name_reply=native_name_reply, interaction_inbox=args.interaction_inbox, native_implicit_recall=args.native_implicit_recall)
    print({key: report[key] for key in ("phase", "ticks", "writer_commits", "workers_terminal")})
    raise SystemExit(0 if report["phase"] == "stopped" and report["workers_terminal"] else 1)


if __name__ == "__main__":
    main()
