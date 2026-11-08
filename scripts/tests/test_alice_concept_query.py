"""Queries use concept weights, numerical prose and the existing worker owner."""
import copy
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

from scripts.alice_memory.concept_memory import ConceptLesson
from scripts.alice_memory.concept_query_language import ConceptQueryLanguage, validate_plan, validate_expression, sha
from scripts.alice_memory.conceptual_mind import ConceptualMind, save, restore
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.language_coordinator import LanguageCoordinator
from scripts.alice_memory.language_process import LanguageProcess
from scripts.alice_memory.persistent_runtime import close_agent, configure_language, run
from test_alice_concept_teaching import FakeLanguage
import test_alice_word_grounding as fixtures

QUESTION = 'Alice, o que dá aplicar "nivo" à entrada (0.3, 0.7)?'


class QueryProtocolContracts(unittest.TestCase):
    def plan(self, question=QUESTION, chain=None):
        return asdict(ConceptQueryLanguage(FakeLanguage({'chain': ['nivo'] if chain is None else chain,
                     'input_fragment': '(0.3, 0.7)', 'uncertain': False})).parse(question))

    def evidence(self):
        return {'kind': 'deduced', 'chain': ['nivo'], 'input': [.3, .7], 'value': [.6, 2.1],
                'premises': {'nivo': 3}, 'query_sha256': sha(QUESTION), 'computed_at': 1.}

    def expression(self):
        return asdict(ConceptQueryLanguage(FakeLanguage({'text': 'O resultado aproximado é (0.6, 2.1).'})).express(self.evidence()))

    def test_parser_receives_only_query_and_does_not_receive_teaching_or_expected_result(self):
        language = FakeLanguage({'chain': ['nivo'], 'input_fragment': '(0.3, 0.7)', 'uncertain': False})
        result = ConceptQueryLanguage(language).parse(QUESTION)
        self.assertEqual(result.chain, ['nivo'])
        self.assertEqual(language.request['messages'][1]['content'], QUESTION)
        self.assertNotIn('0.6', json.dumps(language.request))
        self.assertEqual(language.request['options']['num_gpu'], 0)

    def test_literal_input_invented_name_order_source_and_ambiguous_vectors_are_rejected(self):
        original = self.plan()
        for field, value in (('chain', ['invented']), ('input_fragment', '(0.4, 0.7)'), ('question_sha256', '0' * 64)):
            damaged = copy.deepcopy(original)
            damaged[field] = value
            with self.assertRaises(ValueError):
                validate_plan(damaged, QUESTION, 'fixture')
        with self.assertRaises(ValueError):
            self.plan(QUESTION + ' ou (1, 1)?')
        with self.assertRaises(ValueError):
            self.plan('Aplique "nivo" e depois "outro" a (0.3, 0.7).', ['outro', 'nivo'])
        with self.assertRaises(ValueError):
            self.plan('Aplique "nivo" e depois "nivo" a (0.3, 0.7).')

    def test_vector_in_actual_text_is_checked_not_only_metadata(self):
        original = self.expression()
        for text in ('O resultado é (9, 9).', 'O resultado é (0.6, 2.1) ou (2, 3).',
                     'O resultado é [9, 9].', 'O resultado é [0.6, 2.1] ou (2, 3).',
                     'O resultado é (0.6, 2.1) com certeza 100%.', 'O resultado é (0.6, 2.1) em "inventado".',
                     'Sei a resposta, mas não vou dizer.'):
            damaged = copy.deepcopy(original)
            damaged['text'] = text
            with self.assertRaises(ValueError):
                validate_expression(damaged, self.evidence(), 'fixture')
        modified = self.evidence()
        modified['premises']['nivo'] = 4
        with self.assertRaises(ValueError):
            validate_expression(original, modified, 'fixture')

    def test_decimal_comma_output_and_uncertainty_and_no_torch_worker_import(self):
        bridge = ConceptQueryLanguage(FakeLanguage({'text': 'Aproximadamente (0,6; 2,1).'}))
        self.assertEqual(bridge.express(self.evidence()).text, 'Aproximadamente (0,6; 2,1).')
        brackets = ConceptQueryLanguage(FakeLanguage({'text': 'Aproximadamente [0.6, 2.1].'}))
        self.assertEqual(brackets.express(self.evidence()).text, 'Aproximadamente [0.6, 2.1].')
        uncertain = ConceptQueryLanguage(FakeLanguage({'chain': [], 'input_fragment': None, 'uncertain': True}))
        self.assertTrue(uncertain.parse('O que significa aprender?').uncertain)
        process = subprocess.run([sys.executable, '-c', "import sys; import scripts.alice_memory.concept_query_language; assert 'torch' not in sys.modules"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)


class QueryLifecycleContracts(unittest.TestCase):
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

    def configure(self, mode='normal'):
        self.config.write_text(json.dumps({'delay': .1, 'mode': mode}), encoding='utf-8')

    def factory(self, operation):
        self.assertFalse(any(worker.process.poll() is None for worker in self.workers))
        worker = LanguageProcess(operation, self.folder / 'workers', 15., 'scripts.tests.alice_fake_language_worker',
                                 {'ALICE_FAKE_LANGUAGE_CONFIG': str(self.config)}, retain_files=False)
        self.workers.append(worker)
        return worker

    def core(self, learned=True):
        agent = self.fixture.fixture(False)
        self.fixture.perceive(agent)
        self.fixture.perceive(agent)
        base = LanguageCoordinator(agent, 'http://127.0.0.1:11438', 'fixture', self.folder / 'workers', self.factory,
                                   retry_seconds=.1)
        result = ConceptualMind(base)
        self.addCleanup(result.close)
        if learned:
            self.teach(result)
        return result

    def teach(self, agent, name='nivo', factor=1.):
        for x, y in (((0., 0.), (0., 0.)), ((1., 0.), (2. * factor, 0.)), ((0., 1.), (0., 3. * factor))):
            agent.teach_concept(ConceptLesson(name, x, y, 'external-source', agent.concepts.sequence + 1, agent.clock))

    def until(self, agent, condition):
        deadline = time.monotonic() + 25.
        while not condition():
            self.assertLess(time.monotonic(), deadline)
            agent.tick(.05)
            time.sleep(.02)

    def finished(self, agent, number):
        return agent.concept_queries.jobs[number]['status'] in agent.concept_queries.terminal

    def test_process_query_reads_weights_and_retains_old_episodes_while_sharing_worker(self):
        agent = self.core()
        observations, episodes = agent.temporal.observations, len(agent.mind.actor.session.memory.blocks)
        lessons = agent.concepts.lessons
        base_job = agent.submit('O que aconteceu?')
        lesson_job = agent.submit_lesson('Em "outro", (0, 0) vira (0, 0).')
        number = agent.submit_concept_question(QUESTION)
        self.until(agent, lambda: self.finished(agent, number))
        answer = agent.take_concept_answer(number)
        self.assertEqual(answer['status'], 'completed')
        self.assertTrue(answer['numeric_text_verified'])
        self.assertFalse(answer['free_text_semantics_verified'])
        self.assertFalse(answer['autobiographical_write'])
        self.assertEqual(agent.jobs[base_job]['status'], 'completed')
        self.assertEqual(agent.teaching.jobs[lesson_job]['status'], 'completed')
        self.assertEqual(agent.concepts.lessons, lessons + 1)
        self.assertTrue(torch.allclose(torch.tensor(answer['evidence']['value']), torch.tensor([.6, 2.1]), atol=.003, rtol=0))
        self.assertEqual(agent.temporal.observations, observations)
        self.assertEqual(len(agent.mind.actor.session.memory.blocks), episodes)

    def test_unknown_uncertain_and_changed_coordinates_do_not_become_learned_facts(self):
        agent = self.core(False)
        number = agent.submit_concept_question(QUESTION)
        self.until(agent, lambda: self.finished(agent, number))
        self.assertEqual(agent.take_concept_answer(number)['status'], 'unsupported')
        self.assertEqual(len(self.workers), 1)  # No expression model is asked to invent an answer.
        self.teach(agent)
        for mode, expected in (('query_uncertain', 'uncertain'), ('invent_claim', 'failed')):
            self.configure(mode)
            number = agent.submit_concept_question(QUESTION)
            self.until(agent, lambda: self.finished(agent, number))
            self.assertEqual(agent.take_concept_answer(number)['status'], expected)
        self.assertEqual(agent.concepts.lessons, 3)

    def test_pending_expression_restart_and_retained_answer_use_same_learned_weights(self):
        agent = self.core()
        number = agent.submit_concept_question(QUESTION)
        self.until(agent, lambda: agent.concept_queries.jobs[number]['status'] == 'expressing')
        checkpoint = self.folder / 'pending.pt'
        save(checkpoint, agent)
        agent.close()
        resumed, mind, _ = load_scheduler(checkpoint, self.folder / 'workers', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        self.assertEqual(resumed.concept_queries.jobs[number]['status'], 'ready_to_express')
        self.until(resumed, lambda: self.finished(resumed, number))
        save(checkpoint, resumed)
        resumed.close()
        final, final_mind, _ = load_scheduler(checkpoint, self.folder / 'workers', self.factory)
        self.addCleanup(lambda: close_agent(final, final_mind))
        answer = final.take_concept_answer(number)
        self.assertEqual(answer['status'], 'completed')
        self.assertEqual(final.concepts.lessons, 3)
        self.assertTrue(answer['numeric_text_verified'])

    def test_premise_update_during_expression_or_before_delivery_requires_new_result(self):
        agent = self.core()
        number = agent.submit_concept_question(QUESTION)
        self.until(agent, lambda: agent.concept_queries.jobs[number]['status'] == 'expressing')
        self.teach(agent, factor=2.)
        self.until(agent, lambda: self.finished(agent, number))
        self.assertEqual(agent.concept_queries.jobs[number]['revisions'], 1)
        self.teach(agent, factor=3.)
        self.assertIsNone(agent.take_concept_answer(number))
        self.until(agent, lambda: self.finished(agent, number))
        answer = agent.take_concept_answer(number)
        self.assertEqual(answer['revisions'], 2)
        self.assertEqual(answer['evidence']['premises']['nivo'], 9)
        current = agent.concepts.predict('nivo', [.3, .7])
        self.assertEqual(answer['evidence']['value'], current['value'])

    def test_deferral_expiry_and_language_selection_do_not_lose_query_ownership(self):
        agent = self.core()
        self.configure('deferred')
        number = agent.submit_concept_question(QUESTION, ttl=5.)
        self.until(agent, lambda: agent.concept_queries.jobs[number]['deferrals'] == 1)
        self.assertIsNone(agent.agent.external_worker_owner)
        with self.assertRaises(ValueError):
            configure_language(agent, model='other')
        agent.unobserved_gap(10.)
        agent.tick(0.)
        self.assertEqual(agent.take_concept_answer(number)['error'], 'concept_query_expired')
        self.assertEqual(agent.concepts.lessons, 3)

    def test_runtime_concept_question_and_checkpoint_corruption_validation(self):
        agent = self.core()
        checkpoint = self.folder / 'concept.pt'
        save(checkpoint, agent)
        report = run(self.folder / 'runtime', checkpoint, seconds=3., language_backend='fixture',
                     question=QUESTION, question_mode='concept')
        self.assertEqual(report['concept_query_jobs'][0]['status'], 'completed')
        resumed = run(self.folder / 'runtime', seconds=.2, language_backend='fixture')
        self.assertEqual(resumed['concept_query_jobs'], report['concept_query_jobs'])
        number = agent.submit_concept_question(QUESTION)
        self.until(agent, lambda: self.finished(agent, number))
        original = agent.snapshot()
        for field, value in (('value', [9., 9.]), ('premises', {'nivo': 999}), ('query_sha256', '0' * 64)):
            damaged = copy.deepcopy(original)
            damaged['concept_queries']['jobs'][0]['evidence'][field] = value
            with self.assertRaises(ValueError):
                restore(damaged, self.folder / 'workers', self.factory)

    def test_two_learned_rules_compose_in_explicit_order_and_reversed_order_changes_result(self):
        agent = self.core()
        for x, y in (((0., 0.), (1., 0.)), ((1., 0.), (2., 0.)), ((0., 1.), (1., 1.))):
            agent.teach_concept(ConceptLesson('outro', x, y, 'external-shift', agent.concepts.sequence + 1, agent.clock))
        # First rule's result leaves the second rule's initial coverage. Abstain
        # until external examples cover it; do not weaken the support threshold.
        self.assertFalse(agent.concepts.compose(['nivo', 'outro'], [.3, .7])['supported'])
        for x, y in (((0., 2.), (1., 2.)), ((1., 2.), (2., 2.))):
            agent.teach_concept(ConceptLesson('outro', x, y, 'external-coverage', agent.concepts.sequence + 1, agent.clock))
        values = []
        for question in ('Aplique "nivo" e depois "outro" à entrada (0.3, 0.7).',
                         'Aplique "outro" e depois "nivo" à entrada (0.3, 0.7).'):
            number = agent.submit_concept_question(question)
            self.until(agent, lambda: self.finished(agent, number))
            answer = agent.take_concept_answer(number)
            self.assertEqual(answer['status'], 'completed')
            values.append(answer['evidence']['value'])
        self.assertTrue(torch.allclose(torch.tensor(values[0]), torch.tensor([1.6, 2.1]), atol=.003, rtol=0))
        self.assertTrue(torch.allclose(torch.tensor(values[1]), torch.tensor([2.6, 2.1]), atol=.003, rtol=0))
        self.assertEqual(agent.concepts.lessons, 8)

    def test_old_checkpoint_formats_migrate_and_pending_parse_survives_restart(self):
        agent = self.core()
        payload = agent.snapshot()
        for version in (40, 41):
            legacy = copy.deepcopy(payload)
            legacy['format'] = version
            legacy.pop('native_stream')
            legacy.pop('native')
            legacy.pop('native_queries')
            legacy.pop('native_statements')
            legacy.pop('native_meaning_queries')
            legacy.pop('native_feedbacks')
            legacy.pop('native_namings')
            legacy.pop('interactions')
            legacy.pop('concept_queries')
            if version == 40:
                legacy.pop('teaching')
            migrated = restore(legacy, self.folder / 'workers', self.factory)
            self.addCleanup(migrated.close)
            self.assertEqual(migrated.snapshot()['format'], 57)
            self.assertEqual(migrated.concepts.lessons, 3)
        number = agent.submit_concept_question(QUESTION)
        agent.tick(.05)
        self.assertEqual(agent.concept_queries.jobs[number]['status'], 'parsing')
        checkpoint = self.folder / 'parse.pt'
        save(checkpoint, agent)
        agent.close()
        resumed, mind, _ = load_scheduler(checkpoint, self.folder / 'workers', self.factory)
        self.addCleanup(lambda: close_agent(resumed, mind))
        self.assertEqual(resumed.concept_queries.jobs[number]['status'], 'waiting')
        self.until(resumed, lambda: self.finished(resumed, number))
        self.assertEqual(resumed.take_concept_answer(number)['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
