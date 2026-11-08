"""Contextual Portuguese reports without event/version IDs in the utterance."""
import copy
import json
import subprocess
import sys
import unittest
from dataclasses import asdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_interactions as interactions
import test_alice_concept_query as query_fixtures
from test_alice_concept_teaching import FakeLanguage
from scripts.alice_memory.context_report_language import (LEGACY_REPORT_KIND, REPORT_KIND, ContextReportLanguage,
    language_source, parts, validate_plan, validate_source, subject_value)
from scripts.alice_memory.conceptual_mind import restore
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_sensor import NativeObservation

INITIAL = 'O autor dessa imagem é meu pai.'
CORRECTION = 'Na verdade, foi minha mãe.'


class ContextProtocolContracts(unittest.TestCase):
    def test_parser_has_only_message_and_cannot_invent_role_value_or_provenance(self):
        fake = FakeLanguage({'value_fragment': 'pai'})
        plan = asdict(ContextReportLanguage(fake).parse(INITIAL))
        self.assertEqual(fake.request['messages'][1]['content'], INITIAL)
        self.assertEqual(plan['relation_fragment'], 'autor')
        self.assertEqual(subject_value(plan['subject_fragment']), 'pai')
        self.assertEqual(fake.request['format']['properties']['value_fragment'], {'enum': ['pai', None]})
        self.assertNotIn('moment_ref', json.dumps(fake.request))
        for key, value in (('subject_fragment', 'mãe'), ('relation_fragment', 'cor'), ('message_sha256', '0'*64)):
            with self.assertRaises(ValueError):
                validate_plan({**plan, key: value}, INITIAL, 'fixture')
        correction = ContextReportLanguage(FakeLanguage({'value_fragment': 'mãe'})).parse(CORRECTION)
        self.assertIsNone(correction.relation_fragment)
        self.assertEqual(subject_value(correction.subject_fragment), 'mãe')

    def test_question_hypothesis_negation_and_alternatives_are_not_acquisitions(self):
        for text in ('O autor é meu pai?', 'O autor não é meu pai.', 'Talvez o autor seja meu pai.',
                     'O autor é meu pai ou minha mãe.', 'Ele disse que o autor é meu pai.',
                     'Meu pai é o autor.', 'O autor é meu pai e a cor é azul.'):
            self.assertTrue(ContextReportLanguage(FakeLanguage({'value_fragment': None})).parse(text).uncertain, text)
        self.assertEqual(parts('Porra, a cor disso é azul.')['subject_fragment'], 'azul')
        child = subprocess.run([sys.executable, '-c', "import sys;import scripts.alice_memory.context_report_language;assert 'torch' not in sys.modules"], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_qualified_report_uses_new_guard_and_legacy_sources_still_validate(self):
        text = 'O autor, pelo que parece, é o Dário.'
        model = FakeLanguage({'value_fragment': None})
        plan = asdict(ContextReportLanguage(model).parse(text))
        self.assertTrue(plan['uncertain'])
        self.assertEqual(model.request['format']['properties']['value_fragment'], {'const': None})
        literal = {**plan, 'relation_fragment': 'autor', 'subject_fragment': 'Dário', 'uncertain': False}
        with self.assertRaisesRegex(ValueError, 'Guarded contextual'):
            validate_plan(literal, text, 'fixture')
        legacy = {**literal, 'kind': LEGACY_REPORT_KIND}
        self.assertEqual(validate_plan(legacy, text, 'fixture'), legacy)
        validate_source(language_source(legacy))


class ContextOwnerContracts(unittest.TestCase):
    setUp = interactions.InteractionOwnerContracts.setUp
    configure = interactions.InteractionOwnerContracts.configure
    factory = interactions.InteractionOwnerContracts.factory
    until = interactions.InteractionOwnerContracts.until
    core = interactions.InteractionOwnerContracts.core
    frame = interactions.InteractionOwnerContracts.frame
    inbox = interactions.InteractionOwnerContracts.inbox
    ingest = interactions.InteractionOwnerContracts.ingest
    commits = interactions.InteractionOwnerContracts.commits
    setUpClass = classmethod(interactions.InteractionOwnerContracts.setUpClass.__func__)
    tearDownClass = classmethod(interactions.InteractionOwnerContracts.tearDownClass.__func__)

    def relate(self, core, inbox, text=INITIAL, moment=None, frame=None):
        identifier, _ = self.ingest(core, inbox, 'relate', {'text': text, 'moment': moment, 'frame': frame})
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        self.assertEqual(core.interactions.records[identifier]['status'], 'completed', core.interactions.records[identifier])
        return identifier

    def correct(self, core, inbox, parent, text=CORRECTION):
        identifier, request = self.ingest(core, inbox, 'correct', {'text': text, 'reply_to': parent})
        self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
        return identifier, request

    def test_delayed_report_and_correction_after_new_scene_keep_original_event(self):
        core = self.core(True)
        inbox = self.inbox(core)
        observed = core.native.observations
        self.configure(delay=.3)
        identifier, _ = self.ingest(core, inbox, 'relate', {'text': INITIAL, 'moment': None, 'frame': None})
        core.tick(.05)
        self.frame(core, other=True)
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'pai')
        self.assertFalse(core.native.interpret(1, 'autor')['supported'])
        core.tick(31.)
        correction, request = self.correct(core, inbox, identifier)
        self.assertEqual(core.interactions.records[correction]['status'], 'completed')
        self.assertEqual(core.native.interpret(0, 'autor', 'initial')['subject'], 'pai')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'mãe')
        self.assertEqual(core.native.observations, observed + 2)
        source = core.native.interpretations.records[-1]
        self.assertEqual(source['moment_ref']['id'], 0)
        self.assertEqual(source['language']['kind'], REPORT_KIND)
        self.assertNotIn('subject_fragment', source['language'])
        fallback = self.commits(core, inbox, self.folder / 'contextual')
        fresh, mind, _ = interactions.load_scheduler(fallback, self.folder / 'resumed-context', self.factory)
        self.addCleanup(lambda: interactions.close_agent(fresh, mind))
        fresh.interactions.ingest(request)
        fresh.tick(.1)
        self.assertEqual(len(fresh.native.interpretations.records), 2)
        self.assertEqual(fresh.native.interpret(0, 'autor')['subject'], 'mãe')

    def test_pending_context_survives_restart_and_corrupt_parent_binding_is_refused(self):
        core = self.core(True)
        inbox = self.inbox(core)
        self.configure(delay=.3)
        parent, _ = self.ingest(core, inbox, 'relate', {'text': INITIAL, 'moment': None, 'frame': None})
        core.tick(.05)
        snapshot = core.snapshot()
        self.assertEqual(snapshot['native_statements']['format'], 2)
        core.close()
        fresh = restore(snapshot, self.folder / 'pending-context', self.factory)
        self.addCleanup(fresh.close)
        self.until(fresh, lambda: fresh.interactions.records[parent]['status'] == 'completed')
        child, _ = self.ingest(fresh, inbox, 'correct', {'text': CORRECTION, 'reply_to': parent})
        fresh.tick(.05)
        bad = fresh.snapshot()
        bad['interactions']['records'][-1]['request']['payload']['reply_to'] = 'f'*32
        from scripts.alice_memory.interaction_inbox import digest
        item = bad['interactions']['records'][-1]
        item['request_sha256'] = digest(item['request'])
        with self.assertRaises(ValueError):
            restore(bad, self.folder / 'changed-parent', self.factory)
        self.until(fresh, lambda: fresh.interactions.records[child]['status'] == 'completed')

    def test_correction_of_forgotten_senses_uses_report_provenance_without_new_perception(self):
        core = query_fixtures.QueryLifecycleContracts.core(self, learned=False)
        core.native.moments.close()
        core.native.moments = NativeMoments(1, 1)
        self.frame(core, teach=True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        self.frame(core, other=True)
        self.assertIsNone(core.native.moments.get(0))
        count = core.native.observations
        child, _ = self.correct(core, inbox, parent)
        self.assertEqual(core.interactions.records[child]['status'], 'completed')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'mãe')
        self.assertEqual(core.native.observations, count)
        self.assertIsNone(core.native.moments.get(0))

    def test_stale_parent_and_changed_role_cannot_overwrite_another_interpretation(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        wrong, _ = self.correct(core, inbox, parent, 'A cor disso é azul.')
        self.assertEqual(core.interactions.records[wrong]['status'], 'failed')
        self.assertEqual(len(core.native.interpretations.records), 1)
        corrected, _ = self.correct(core, inbox, parent)
        self.assertEqual(core.interactions.records[corrected]['status'], 'completed')
        stale, _ = self.correct(core, inbox, parent, 'Na verdade, foi João.')
        self.assertEqual(core.interactions.records[stale]['status'], 'failed')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'mãe')

    def test_uncertain_invented_and_unbound_role_do_not_teach_and_erased_weights_abstain(self):
        core = self.core(True)
        inbox = self.inbox(core)
        for mode, text in (('normal', 'O autor é meu pai?'), ('invent_claim', INITIAL), ('normal', CORRECTION)):
            self.configure(mode)
            identifier, _ = self.ingest(core, inbox, 'relate', {'text': text, 'moment': None, 'frame': None})
            self.until(core, lambda: core.interactions.records[identifier]['status'] == 'failed')
            self.assertFalse(core.native.interpretations.records)
        self.configure()
        self.relate(core, inbox)
        core.native.interpretations.bank.weights.zero_()
        self.assertFalse(core.native.interpret(0, 'autor')['supported'])

    def test_new_reports_with_uncertainty_cannot_use_legacy_guard_to_write(self):
        core = self.core(True)
        inbox = self.inbox(core)
        text = 'O autor provavelmente é João.'
        for mode in ('normal', 'legacy_context_report'):
            self.configure(mode)
            identifier, _ = self.ingest(core, inbox, 'relate', {'text': text, 'moment': 0, 'frame': None})
            self.until(core, lambda: core.interactions.records[identifier]['status'] in ('completed', 'failed'))
            result = core.interactions.records[identifier]['result']
            self.assertEqual(result['status'], 'failed')
            self.assertFalse(core.native.interpretations.records)
            if mode == 'legacy_context_report':
                self.assertIn('requires the current literal guard', result['error'])

    def test_declared_image_cannot_bind_implicitly_to_a_later_audio_only_event(self):
        core = self.core(True)
        inbox = self.inbox(core)
        at = core.clock + .1
        audio = NativeObservation('audio', torch.nn.functional.one_hot(torch.tensor(71), 128).float(),
                                  at, core.native.observations, 'a'*64)
        core.perceive_native([audio], .1)
        identifier, _ = self.ingest(core, inbox, 'relate', {'text': INITIAL, 'moment': None, 'frame': None})
        core.interactions.poll()
        self.assertEqual(core.interactions.records[identifier]['status'], 'failed')
        self.assertFalse(core.native.interpretations.records)
        self.assertFalse(core.native_statements.jobs)
        self.relate(core, inbox, moment=0)
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'pai')

    def test_pending_correction_protects_parent_when_other_confirmed_messages_are_pruned(self):
        core = self.core(True)
        inbox = self.inbox(core)
        parent = self.relate(core, inbox)
        self.commits(core, inbox, self.folder / 'confirmed-parent')
        child, _ = self.ingest(core, inbox, 'correct', {'text': CORRECTION, 'reply_to': parent})
        for _ in range(40):
            identifier, _ = self.ingest(core, inbox, 'correct', {'text': CORRECTION, 'reply_to': 'f'*32})
            core.interactions.dispatch(core.interactions.records[identifier])
            record = core.interactions.records[identifier]
            self.assertEqual(record['status'], 'failed')
            # Publication is an input to this pruning unit; durable receipts
            # themselves are exercised by the other persistence contracts.
            record['published'] = record['revision']
        self.assertIn(parent, core.interactions.records)
        self.assertIn(child, core.interactions.records)
        self.assertLessEqual(len(core.interactions.records), 32)
        self.until(core, lambda: core.interactions.records[child]['status'] == 'completed')
        self.assertEqual(core.native.interpret(0, 'autor')['subject'], 'mãe')

    def test_confirmed_parent_cannot_switch_to_another_report_after_its_job_is_taken(self):
        core = self.core(True)
        inbox = self.inbox(core)
        self.relate(core, inbox)
        other = self.relate(core, inbox, 'A cor dessa imagem é azul.')
        self.commits(core, inbox, self.folder / 'two-confirmed-reports')
        self.assertFalse(core.native_statements.jobs)
        saved = core.snapshot()
        record = next(item for item in saved['interactions']['records'] if item['request']['id'] == other)
        record['result']['learning']['version'] = 0
        with self.assertRaises(ValueError):
            restore(saved, self.folder / 'wrong-confirmed-version', self.factory)


if __name__ == '__main__':
    unittest.main()
