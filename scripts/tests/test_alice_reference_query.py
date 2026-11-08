"""Message-referenced interpretation survives lost senses and changes of belief."""
import copy
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_context_report as contexts
import test_alice_concept_query as query_fixtures
from test_alice_concept_teaching import FakeLanguage
from scripts.alice_memory.reference_language import ReferenceLanguage, validate_plan, phrases, validate_expression
from scripts.alice_memory.native_interpretation import NativeStatement
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.conceptual_mind import restore


class ReferenceProtocolContracts(unittest.TestCase):
    def test_model_only_selects_perspective_and_cannot_change_literal_view(self):
        for question, view in (('Quem era antes?', 'initial'), ('E agora?', 'current'), ('O que mudou?', 'comparison')):
            fake = FakeLanguage({'view': view})
            plan = asdict(ReferenceLanguage(fake).parse(question))
            self.assertEqual(fake.request['messages'][1]['content'], question)
            self.assertNotIn('moment_ref', json.dumps(fake.request))
            with self.assertRaises(ValueError):
                validate_plan({**plan, 'view': 'initial' if view != 'initial' else 'current'}, question, 'fixture')
        self.assertTrue(ReferenceLanguage(FakeLanguage({'view': 'uncertain'})).parse('Explique a física quântica.').uncertain)
        child = subprocess.run([sys.executable, '-c', "import sys;import scripts.alice_memory.reference_language;assert 'torch' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)


class ReferenceOwnerContracts(unittest.TestCase):
    setUp = contexts.ContextOwnerContracts.setUp
    configure = contexts.ContextOwnerContracts.configure
    factory = contexts.ContextOwnerContracts.factory
    until = contexts.ContextOwnerContracts.until
    core = contexts.ContextOwnerContracts.core
    frame = contexts.ContextOwnerContracts.frame
    inbox = contexts.ContextOwnerContracts.inbox
    ingest = contexts.ContextOwnerContracts.ingest
    commits = contexts.ContextOwnerContracts.commits
    relate = contexts.ContextOwnerContracts.relate
    correct = contexts.ContextOwnerContracts.correct
    setUpClass = classmethod(contexts.ContextOwnerContracts.setUpClass.__func__)
    tearDownClass = classmethod(contexts.ContextOwnerContracts.tearDownClass.__func__)

    def answer(self, core, inbox, parent, question):
        identifier, _ = self.ingest(core, inbox, 'recall', {'text': question, 'about': parent})
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed', core.interactions.records[identifier])
        return identifier, core.interactions.records[identifier]['result']['data']

    def test_current_initial_and_comparison_use_original_message_even_after_correction(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        self.frame(core, other=True)
        self.correct(core, inbox, parent)
        observed = core.native.observations
        for question, view, subject in (('Quem era antes?', 'initial', 'pai'), ('E agora?', 'current', 'mãe')):
            _, answer = self.answer(core, inbox, parent, question)
            self.assertEqual(answer['evidence']['reports'][view]['subject'], subject)
            self.assertEqual(answer['evidence']['moment_ref']['id'], 0)
            self.assertFalse(answer['evidence']['reports'][view]['directly_observed'])
        identifier, compare = self.answer(core, inbox, parent, 'O que mudou?')
        self.assertIn('"pai"', compare['proposal']['text'])
        self.assertIn('"mãe"', compare['proposal']['text'])
        self.assertEqual(core.native.observations, observed)
        self.commits(core, inbox, self.folder / 'referenced')
        self.assertIsNotNone(inbox.receipt(identifier))

    def test_semantic_answer_outlives_sensory_episode_without_recreating_it(self):
        core = query_fixtures.QueryLifecycleContracts.core(self, learned=False)
        core.native.moments.close()
        core.native.moments = NativeMoments(1, 1)
        self.frame(core, teach=True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        self.frame(core, other=True)
        self.assertIsNone(core.native.moments.get(0))
        self.correct(core, inbox, parent)
        observed, lifetime = core.native.observations, core.native.moments.next_id
        _, answer = self.answer(core, inbox, parent, 'E agora?')
        self.assertEqual(answer['evidence']['reports']['current']['subject'], 'mãe')
        self.assertFalse(answer['evidence']['sensory_episode_retained'])
        self.assertIn('não está mais retido', answer['proposal']['text'])
        self.assertIsNone(core.native.moments.get(0))
        self.assertEqual((core.native.observations, core.native.moments.next_id), (observed, lifetime))

    def test_erased_interpretation_abstains_even_when_message_and_names_still_exist(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        core.native.interpretations.bank.weights.zero_()
        _, answer = self.answer(core, inbox, parent, 'E agora?')
        self.assertFalse(answer['evidence']['reports']['current']['supported'])
        self.assertIsNone(answer['evidence']['reports']['current']['subject'])
        self.assertNotIn('"pai"', answer['proposal']['text'])
        with self.assertRaises(ValueError):
            validate_expression({**answer['proposal'], 'text': 'Eu vi seu pai.'}, answer['evidence'], core.agent.model)

    def test_correction_before_confirmation_recomputes_referenced_reply(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        identifier, _ = self.answer(core, inbox, parent, 'E agora?')
        core.teach_native_interpretation(NativeStatement(0, 'autor', 'mãe', 'a'*64, 1, core.clock, 'person', (0,)))
        core.interactions.poll()
        self.assertEqual(core.interactions.records[identifier]['status'], 'running')
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(core.interactions.records[identifier]['result']['data']['evidence']['reports']['current']['subject'], 'mãe')

    def test_pending_and_completed_queries_restore_and_changed_parent_is_rejected(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        self.configure(delay=.3)
        identifier, request = self.ingest(core, inbox, 'recall', {'text': 'E agora?', 'about': parent})
        core.tick(.05)
        snapshot = core.snapshot()
        self.assertEqual(snapshot['native_meaning_queries']['format'], 2)
        core.close()
        fresh = restore(snapshot, self.folder / 'pending-reference', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: fresh.interactions.records[identifier]['status'] == 'completed')
        bad = copy.deepcopy(fresh.snapshot())
        record = next(item for item in bad['interactions']['records'] if item['request']['id'] == identifier)
        record['request']['payload']['about'] = 'f'*32
        from scripts.alice_memory.interaction_inbox import digest
        record['request_sha256'] = digest(record['request'])
        with self.assertRaises(ValueError):
            restore(bad, self.folder / 'invalid-reference', self.factory)
        fallback = self.commits(fresh, inbox, self.folder / 'reference-store')
        resumed, mind, _ = contexts.interactions.load_scheduler(fallback, self.folder / 'fallback-reference', self.factory)
        self.addCleanup(lambda: contexts.interactions.close_agent(resumed, mind))
        resumed.interactions.ingest(request)
        resumed.tick(.1)
        self.assertEqual(len(resumed.native.interpretations.records), 1)
        self.assertEqual(resumed.interactions.records[identifier]['result']['data']['evidence']['reports']['current']['subject'], 'pai')

    def test_missing_context_and_unrelated_question_do_not_invent_information(self):
        core = self.core(True)
        inbox = self.inbox(core)
        missing, _ = self.ingest(core, inbox, 'recall', {'text': 'E agora?', 'about': 'f'*32})
        core.interactions.poll()
        self.assertEqual(core.interactions.records[missing]['status'], 'failed')
        self.assertFalse(core.native_meaning_queries.jobs)
        parent = self.relate(core, inbox)
        unsupported, _ = self.ingest(core, inbox, 'recall', {'text': 'Qual é a capital do Japão?', 'about': parent})
        self.until(core, lambda: core.interactions.records[unsupported]['status'] == 'failed')
        self.assertIsNone(core.interactions.records[unsupported]['result']['data'])

    def test_plain_and_referenced_queries_share_queue_and_legacy_plain_format_migrates(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        plain = core.submit_native_meaning_question('Qual é a informação atual de "maruvi" sobre "autor", pela imagem?')
        binding = {'version': 0, 'moment_ref': core.native.interpretations.records[0]['moment_ref'], 'relation': 'autor'}
        bound = core.submit_reference_question('E agora?', binding)
        saved = core.snapshot()
        fresh = restore(saved, self.folder / 'mixed-queue', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: all(fresh.native_meaning_queries.jobs[index]['status'] == 'completed' for index in (plain, bound)))
        self.assertEqual(fresh.native_meaning_queries.jobs[plain]['evidence']['reports']['current']['subject'], 'pai')
        self.assertEqual(fresh.native_meaning_queries.jobs[bound]['evidence']['reports']['current']['subject'], 'pai')
        legacy = copy.deepcopy(saved)
        jobs = legacy['native_meaning_queries']['jobs']
        legacy['native_meaning_queries']['format'] = 1
        legacy['native_meaning_queries']['jobs'] = [item for item in jobs if item['binding'] is None]
        for item in legacy['native_meaning_queries']['jobs']:
            item.pop('binding')
        migrated = restore(legacy, self.folder / 'legacy-meaning-queue', self.factory)
        self.addCleanup(migrated.close)
        self.assertEqual(migrated.native_meaning_queries.snapshot()['format'], 2)
        self.assertEqual(migrated.native_meaning_queries.jobs[plain]['binding'], None)
        self.assertTrue(all(worker.process.poll() is not None for worker in self.workers))


if __name__ == '__main__':
    unittest.main()
