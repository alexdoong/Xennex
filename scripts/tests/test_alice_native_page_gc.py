"""Native page reclamation preserves both generations and uncertain ownership."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_word_grounding as fixtures
import test_alice_native_page_store as page_tests
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.native_fast_weights import NativeFastWeights
from scripts.alice_memory.native_moments import pack
from scripts.alice_memory.native_page_gc import read_journal, register
from scripts.alice_memory.native_page_store import page_path, write_bytes
from scripts.alice_memory.persistent_runtime import close_agent


class NativeGcContracts(unittest.TestCase):
    setUp = page_tests.NativePageContracts.setUp
    perceive = page_tests.NativePageContracts.perceive
    commit = page_tests.NativePageContracts.commit

    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def directory(self):
        return self.store.root / 'native-pages'

    def orphan(self, seed=71, registered=True):
        generator = torch.Generator().manual_seed(seed)
        bank = NativeFastWeights()
        key = torch.randn(132, generator=generator, dtype=torch.float64) * .1
        value = torch.randn(384, generator=generator, dtype=torch.float64) * .1
        bank.write(key, value)
        raw = pack(bank)
        record = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
        if registered:
            register(self.directory(), [record])
        write_bytes(page_path(self.directory(), record), raw)
        return record

    def assert_restorable(self):
        for path, _ in self.store.candidates():
            agent, mind, _ = load_scheduler(path)
            close_agent(agent, mind)

    def test_registered_unused_page_is_removed_and_current_previous_are_restorable(self):
        self.perceive(0)
        self.commit()
        self.perceive(1)
        self.commit()
        orphan = self.orphan()
        outcome = self.store.collect_native_pages()
        self.assertEqual(outcome['status'], 'collected')
        self.assertEqual(outcome['removed_pages'], 1)
        self.assertEqual(outcome['removed_bytes'], orphan['size'])
        self.assertFalse(page_path(self.directory(), orphan).exists())
        self.assertNotIn(orphan['sha256'], read_journal(self.directory()))
        self.assert_restorable()

    def test_previous_exclusive_page_survives_until_both_generation_references_expire(self):
        self.perceive(0)
        first = self.commit()
        # Save an earlier portable state outside the runtime before branching.
        from scripts.alice_memory.conceptual_mind import save
        earlier = self.root / 'earlier.pt'
        save(earlier, self.agent)
        self.perceive(1)
        second = self.commit()
        exclusive = second.payload['native']['moments']['pages'][1]
        earlier_agent, earlier_mind, _ = load_scheduler(earlier)
        try:
            self.store.submit(self.store.capture(earlier_agent), earlier_agent.clock)
            self.assertEqual(self.store.finish()['status'], 'committed')
            self.assertTrue(page_path(self.directory(), exclusive).exists())
            self.assertEqual(self.store.collect_native_pages()['removed_pages'], 0)
            self.store.submit(self.store.capture(earlier_agent), earlier_agent.clock)
            final = self.store.finish()
            self.assertEqual(final['status'], 'committed')
            self.assertEqual(final['native_page_gc']['after']['removed_pages'], 1)
            self.assertFalse(page_path(self.directory(), exclusive).exists())
            self.assertTrue(page_path(self.directory(), first.payload['native']['moments']['pages'][0]).exists())
            self.assert_restorable()
        finally:
            close_agent(earlier_agent, earlier_mind)

    def test_unknown_valid_page_and_unrelated_files_are_never_claimed_or_deleted(self):
        self.perceive(0)
        self.commit()
        unknown = self.orphan(registered=False)
        private = self.directory() / 'private.txt'
        private.write_bytes(b'unrelated')
        owned = self.orphan(seed=29)
        result = self.store.collect_native_pages()
        self.assertEqual(result['removed_pages'], 1)
        self.assertFalse(page_path(self.directory(), owned).exists())
        self.assertTrue(page_path(self.directory(), unknown).exists())
        self.assertEqual(private.read_bytes(), b'unrelated')
        self.assertNotIn(unknown['sha256'], read_journal(self.directory()))

    def test_altered_owned_page_is_preserved_and_reported(self):
        self.perceive(0)
        self.commit()
        altered = self.orphan()
        path = page_path(self.directory(), altered)
        corrupted = b'!' * altered['size']
        path.write_bytes(corrupted)
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['removed_pages'], 0)
        self.assertTrue(result['errors'])
        self.assertEqual(path.read_bytes(), corrupted)
        self.assertIn(altered['sha256'], read_journal(self.directory()))

    def test_corrupt_retained_generation_prevents_all_deletion(self):
        self.perceive(0)
        self.commit()
        self.perceive(1)
        self.commit()
        orphan = self.orphan()
        path = self.store.path(self.store.manifest['previous']['file'])
        path.write_bytes(b'corrupt')
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['removed_pages'], 0)
        self.assertTrue(page_path(self.directory(), orphan).exists())

    def test_extra_checkpoint_prevents_collection_even_when_not_in_pointer(self):
        self.perceive(0)
        self.commit()
        orphan = self.orphan()
        extra = self.store.root / 'saved-by-user.pt'
        extra.write_bytes(b'unrelated checkpoint')
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'skipped')
        self.assertTrue(page_path(self.directory(), orphan).exists())
        self.assertEqual(extra.read_bytes(), b'unrelated checkpoint')

    def test_interrupted_write_intent_can_be_reclaimed_without_touching_missing_protected_pages(self):
        self.perceive(0)
        current = self.commit()
        missing_intent = {'sha256': 'a' * 64, 'size': 100}
        register(self.directory(), [missing_intent])
        result = self.store.collect_native_pages()
        self.assertEqual(result['missing_entries'], 1)
        self.assertNotIn(missing_intent['sha256'], read_journal(self.directory()))
        orphan = self.orphan()
        protected = current.payload['native']['moments']['pages'][0]
        page_path(self.directory(), protected).unlink()
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'skipped')
        self.assertTrue(page_path(self.directory(), orphan).exists())

    def test_partial_delete_and_journal_failure_are_reported_and_retryable(self):
        self.perceive(0)
        self.commit()
        one, two = self.orphan(), self.orphan(29)
        first_path = page_path(self.directory(), one)
        original = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path == first_path:
                raise OSError('injected deletion failure')
            return original(path, *args, **kwargs)
        with patch.object(type(first_path), 'unlink', interrupted):
            result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['removed_pages'], 1)
        self.assertTrue(first_path.exists())
        self.assertFalse(page_path(self.directory(), two).exists())
        with patch('scripts.alice_memory.native_page_gc.save_journal', side_effect=OSError('journal interrupted')):
            result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['removed_pages'], 1)
        self.assertIn(one['sha256'], read_journal(self.directory()))
        self.assertEqual(self.store.collect_native_pages()['missing_entries'], 1)
        self.assert_restorable()

    def test_inflight_capture_references_are_protected_before_pointer_failure(self):
        self.perceive(0)
        self.commit()
        orphan = self.orphan()
        self.perceive(1)
        pending = self.store.capture(self.agent)
        record, raw = pending.writes[0]
        register(self.directory(), [record])
        write_bytes(page_path(self.directory(), record), raw)
        with patch('scripts.alice_memory.runtime_store.atomic_json', side_effect=OSError('pointer failure')):
            self.store.submit(pending, self.agent.clock)
            result = self.store.finish()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(page_path(self.directory(), record).exists())
        self.assertFalse(page_path(self.directory(), orphan).exists())
        self.assert_restorable()
        self.commit()
        self.assertTrue(page_path(self.directory(), record).exists())

    def test_owner_journal_path_and_busy_writer_prevent_unsafe_collection(self):
        from concurrent.futures import Future
        self.perceive(0)
        self.commit()
        orphan = self.orphan()
        path = self.directory() / 'owned.json'
        original = path.read_bytes()
        for invalid in ({'format': True, 'owned': {}}, {'format': 1, 'owned': {'../outside': 100}}):
            path.write_text(json.dumps(invalid))
            result = self.store.collect_native_pages()
            self.assertEqual(result['status'], 'skipped')
            self.assertTrue(page_path(self.directory(), orphan).exists())
        path.write_bytes(original)
        self.store.future = Future()
        try:
            with self.assertRaisesRegex(ValueError, 'busy'):
                self.store.collect_native_pages()
        finally:
            self.store.future = None

    def test_collection_before_disk_admission_releases_space_for_new_page(self):
        self.perceive(0)
        current = self.commit()
        orphan = self.orphan()
        self.perceive(1)
        pending = self.store.capture(self.agent)
        active = current.payload['native']['moments']['pages'][0]['size']
        new = pending.writes[0][0]['size']
        with patch('scripts.alice_memory.native_page_store.MAX_BYTES', active + new):
            self.store.submit(pending, self.agent.clock)
            result = self.store.finish()
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(result['native_page_gc']['before']['removed_pages'], 1)
        self.assertFalse(page_path(self.directory(), orphan).exists())
        self.assert_restorable()

    def test_registered_hash_matching_non_weight_data_is_preserved(self):
        self.perceive(0)
        self.commit()
        raw = b'Ordinary text, not a native weight archive.'
        record = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
        register(self.directory(), [record])
        path = page_path(self.directory(), record)
        write_bytes(path, raw)
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['removed_pages'], 0)
        self.assertEqual(path.read_bytes(), raw)
        self.assertIn(record['sha256'], read_journal(self.directory()))

    def test_self_consistent_unreadable_checkpoint_suspends_deletion(self):
        from scripts.alice_memory.runtime_store import atomic_json, digest
        self.perceive(0)
        self.commit()
        orphan = self.orphan()
        record = self.store.manifest['current']
        path = self.store.path(record['file'])
        path.write_bytes(b'not a torch checkpoint')
        record.update(size=path.stat().st_size, sha256=digest(path))
        atomic_json(self.store.root / 'current.json', self.store.manifest)
        result = self.store.collect_native_pages()
        self.assertEqual(result['status'], 'skipped')
        self.assertEqual(result['removed_pages'], 0)
        self.assertTrue(page_path(self.directory(), orphan).exists())


if __name__ == '__main__':
    unittest.main()
