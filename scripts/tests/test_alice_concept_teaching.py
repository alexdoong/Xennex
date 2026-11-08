"""Literal parser contracts, shared worker ownership and persistent teaching."""
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.concept_language import ConceptLanguage, LessonPlan, pair, validate_plan
from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.language import AdmissionDeferred
from scripts.alice_memory.language_coordinator import LanguageCoordinator
from scripts.alice_memory.language_process import LanguageProcess
from scripts.alice_memory.persistent_runtime import close_agent, run
from scripts.alice_memory.runtime_snapshot import capture
from scripts.alice_memory.loop_checkpoint import atomic_write
import test_alice_word_grounding as fixtures

TEXT = 'Aprende comigo: no conceito "nivo", (1, 0) vira (2, 0).'


class FakeLanguage:
    model = 'fixture'

    def __init__(self, draft):
        self.draft = draft
        self.request = None

    def metadata(self):
        return {'digest': 'fixture-digest'}

    def admit(self, metadata):
        pass

    def _request(self, path, request):
        self.request = request
        return {'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(self.draft)}}


class LessonProtocolContracts(unittest.TestCase):
    def plan(self):
        language = FakeLanguage({'concept': 'nivo', 'input_fragment': '(1, 0)', 'output_fragment': '(2, 0)', 'uncertain': False})
        return asdict(ConceptLanguage(language).parse(TEXT))

    def test_parser_binds_literal_examples_and_source_without_computing_a_target(self):
        plan = self.plan()
        self.assertEqual(pair(plan['input_fragment']), [1., 0.])
        self.assertEqual(pair(plan['output_fragment']), [2., 0.])
        self.assertEqual(plan['question_sha256'], hashlib.sha256(TEXT.encode()).hexdigest())
        self.assertEqual(plan['kind'], 'external_literal_lesson')

    def test_invented_reversed_renamed_or_other_source_proposals_are_rejected(self):
        original = self.plan()
        for field, value in (('output_fragment', '(3, 0)'), ('concept', 'another'), ('input_fragment', '(2, 0)'),
                             ('question_sha256', 'a' * 64), ('uncertain', True)):
            damaged = copy.deepcopy(original)
            damaged[field] = value
            with self.assertRaises(ValueError):
                validate_plan(damaged, TEXT, 'fixture')

    def test_uncertainty_carries_no_new_knowledge_and_admission_does_not_generate(self):
        language = FakeLanguage({'concept': None, 'input_fragment': None, 'output_fragment': None, 'uncertain': True})
        result = ConceptLanguage(language).parse('O que seria aprender?')
        self.assertTrue(result.uncertain)
        self.assertIsNone(result.concept)
        def deferred(metadata):
            raise AdmissionDeferred({'used_bytes': 100, 'total_bytes': 100}, 1)
        language.admit = deferred
        language.request = None
        with self.assertRaises(AdmissionDeferred):
            ConceptLanguage(language).parse(TEXT)
        self.assertIsNone(language.request)

    def test_portuguese_decimal_comma_and_identity_examples_keep_literal_values(self):
        self.assertEqual(pair('(1,5; -2,25)'), [1.5, -2.25])
        self.assertEqual(pair('(1e-2, -.25)'), [.01, -.25])
        for invalid in ('(true, 0)', '(nan, 0)', '(65, 0)', '(1, 2, 3)', '(1+2, 0)'):
            with self.assertRaises(ValueError):
                pair(invalid)
        language = FakeLanguage({'concept': 'nivo', 'input_fragment': '(1, 0)', 'output_fragment': '(1, 0)', 'uncertain': False})
        self.assertFalse(ConceptLanguage(language).parse('Em "nivo", (1, 0) vira (1, 0).').uncertain)

    def test_worker_contract_remains_lightweight_without_torch(self):
        process = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.concept_language; assert 'torch' not in sys.modules"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_literal_grounding_does_not_promote_negated_or_tentative_examples(self):
        language = FakeLanguage({'concept': 'nivo', 'input_fragment': '(1, 0)', 'output_fragment': '(2, 0)', 'uncertain': False})
        for text in ('Em "nivo", (1, 0) não vira (2, 0).', 'Em "nivo", (1, 0) talvez vire (2, 0).',
                     'Não é verdade que em "nivo", (1, 0) vira (2, 0).'):
            with self.assertRaises(ValueError):
                ConceptLanguage(language).parse(text)
        self.assertFalse(ConceptLanguage(language).parse('Não esquece: em "nivo", (1, 0) vira (2, 0).').uncertain)


class ConversationalTeachingContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(self.fixture.doCleanups)
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config = self.folder / 'fixture.json'
        self.configure()
        self.workers = []
        self.maximum_alive = 0

    def configure(self, mode='normal'):
        self.config.write_text(json.dumps({'delay': .15, 'mode': mode}), encoding='utf-8')

    def factory(self, operation):
        alive = sum(worker.process.poll() is None for worker in self.workers)
        self.assertEqual(alive, 0, 'Two workers attempted to use language concurrently.')
        worker = LanguageProcess(operation, self.folder / 'workers', 10., 'scripts.tests.alice_fake_language_worker',
                                 {'ALICE_FAKE_LANGUAGE_CONFIG': str(self.config)}, retain_files=False)
        self.workers.append(worker)
        self.maximum_alive = max(self.maximum_alive, alive + 1)
        return worker

    def core(self):
        agent = self.fixture.fixture(False)
        self.fixture.perceive(agent)
        self.fixture.perceive(agent)
        base = LanguageCoordinator(agent, 'http://127.0.0.1:11438', 'fixture', self.folder / 'workers', self.factory,
                                   retry_seconds=.1)
        result = ConceptualMind(base)
        self.addCleanup(result.close)
        return result

    def until(self, agent, condition):
        deadline = time.monotonic() + 20.
        while not condition():
            self.assertLess(time.monotonic(), deadline)
            agent.tick(.05)
            time.sleep(.02)

    def test_real_process_teaching_learns_and_shares_one_worker_with_conversation(self):
        agent = self.core()
        observations = agent.temporal.observations
        episodes = len(agent.mind.actor.session.memory.blocks)
        base_job = agent.submit('O que aconteceu?')
        numbers = [agent.submit_lesson(text) for text in (
            'No conceito "nivo", (0, 0) vira (0, 0).',
            TEXT,
            'Porra, no conceito "nivo", (0, 1) vira (0, 3).')]
        self.until(agent, lambda: all(agent.teaching.jobs[number]['status'] == 'completed' for number in numbers))
        self.assertEqual(agent.jobs[base_job]['status'], 'completed')
        self.assertEqual(self.maximum_alive, 1)
        self.assertEqual(agent.concepts.lessons, 3)
        result = agent.concepts.predict('nivo', [.3, .7])
        self.assertTrue(result['supported'])
        self.assertTrue(torch.allclose(torch.tensor(result['value']), torch.tensor([.6, 2.1]), atol=.003, rtol=0))
        self.assertEqual(agent.temporal.observations, observations)
        self.assertEqual(len(agent.mind.actor.session.memory.blocks), episodes)

    def test_bad_or_uncertain_language_never_teaches_and_worker_reservation_is_released(self):
        for mode, expected in (('invent_claim', 'failed'), ('lesson_uncertain', 'uncertain')):
            self.configure(mode)
            agent = self.core()
            number = agent.submit_lesson(TEXT)
            self.until(agent, lambda: agent.teaching.jobs[number]['status'] == expected)
            self.assertEqual(agent.concepts.lessons, 0)
            self.assertIsNone(agent.agent.external_worker_owner)
            agent.close()

    def test_pending_and_completed_lessons_resume_without_replaying_a_committed_update(self):
        agent = self.core()
        number = agent.submit_lesson(TEXT)
        agent.tick(.05)
        self.assertEqual(agent.teaching.jobs[number]['status'], 'parsing')
        checkpoint = self.folder / 'mind.pt'
        save(checkpoint, agent)
        agent.close()
        resumed, mind, _ = load_scheduler(checkpoint, self.folder / 'workers', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        self.assertEqual(resumed.teaching.jobs[number]['status'], 'waiting')
        self.until(resumed, lambda: resumed.teaching.jobs[number]['status'] == 'completed')
        self.assertEqual(resumed.concepts.lessons, 1)
        atomic_write(checkpoint, capture(resumed))
        resumed.close()
        final, final_mind, _ = load_scheduler(checkpoint, self.folder / 'workers', self.factory)
        self.addCleanup(lambda: close_agent(final, final_mind))
        for _ in range(3):
            final.tick(.1)
        self.assertEqual(final.concepts.lessons, 1)
        self.assertEqual(final.take_lesson(number)['status'], 'completed')
        self.assertFalse(final.teaching.jobs)

    def test_resource_deferral_preserves_job_and_self_origin_is_refused(self):
        self.configure('deferred')
        agent = self.core()
        with self.assertRaises(ValueError):
            agent.submit_lesson(TEXT, origin='self')
        number = agent.submit_lesson(TEXT)
        self.until(agent, lambda: agent.teaching.jobs[number]['deferrals'] == 1)
        self.assertEqual(agent.concepts.lessons, 0)
        self.configure()
        self.until(agent, lambda: agent.teaching.jobs[number]['status'] == 'completed')
        self.assertEqual(agent.concepts.lessons, 1)

    def test_offline_expiry_cancels_teaching_without_fabricating_learning(self):
        agent = self.core()
        number = agent.submit_lesson(TEXT, ttl=5.)
        agent.tick(.05)
        agent.unobserved_gap(10.)
        agent.tick(0.)
        self.assertEqual(agent.teaching.jobs[number]['status'], 'failed')
        self.assertEqual(agent.teaching.jobs[number]['error'], 'lesson_expired')
        self.assertEqual(agent.concepts.lessons, 0)
        self.assertIsNone(agent.agent.external_worker_owner)

    def test_runtime_bootstrap_text_lesson_commits_and_resumes_same_update(self):
        agent = self.core()
        checkpoint, store = self.folder / 'language.pt', self.folder / 'runtime'
        save(checkpoint, agent)
        first = run(store, checkpoint, seconds=2., language_backend='fixture', lesson=TEXT)
        self.assertEqual(first['teaching_jobs'][0]['status'], 'completed')
        second = run(store, seconds=.2, language_backend='fixture')
        self.assertTrue(second['recovery']['resumed'])
        self.assertEqual(first['teaching_jobs'], second['teaching_jobs'])
        self.assertEqual(second['teaching_jobs'][0]['learning']['version'], 1)

    def test_language_selection_preserves_provenance_and_refuses_changes_with_queued_work(self):
        from scripts.alice_memory.persistent_runtime import configure_language
        agent = self.core()
        configure_language(agent, model='qwen3.5:0.8b-q8_0')
        self.assertEqual(agent.model, 'qwen3.5:0.8b-q8_0')
        agent.submit_lesson(TEXT)
        with self.assertRaises(ValueError):
            configure_language(agent, model='another-model')
        self.assertEqual(agent.model, 'qwen3.5:0.8b-q8_0')
        with self.assertRaises(ValueError):
            configure_language(agent, endpoint='http://example.com:11438')
        self.assertEqual(agent.endpoint, 'http://127.0.0.1:11438')


if __name__ == '__main__':
    unittest.main()
