"""Incremental weight pages, detached capture, crash safety and fresh recovery."""
import copy
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_alice_word_grounding as fixtures
from scripts.alice_memory.conceptual_mind import ConceptualMind, save
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.native_moments import NativeMoments
from scripts.alice_memory.native_page_store import PendingNativeCheckpoint, page_path, write_bytes
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.persistent_runtime import close_agent, restore_runtime, run
from scripts.alice_memory.runtime_store import RuntimeStore


def packet(index, modality='image', at=None):
    vector = torch.nn.functional.one_hot(torch.tensor(index + (32 if modality == 'audio' else 0)), 128).float()
    return NativeObservation(modality, vector, float(index + 1) if at is None else at, index, f'{index:064x}')


class NativePageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.WrittenGroundingTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.WrittenGroundingTests.tearDownClass()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        fixture = fixtures.WrittenGroundingTests()
        self.addCleanup(fixture.doCleanups)
        self.agent = ConceptualMind(fixture.fixture(False))
        self.addCleanup(self.agent.close)
        self.store = RuntimeStore(self.root / 'runtime')
        self.addCleanup(self.store.close)

    def perceive(self, index):
        self.agent.perceive_native([packet(index), packet(index, 'audio')], 1.)

    def commit(self):
        payload = self.store.capture(self.agent)
        self.assertTrue(self.store.submit(payload, self.agent.clock))
        self.last_commit = self.store.finish()
        self.assertEqual(self.last_commit['status'], 'committed')
        return payload

    def test_only_new_weight_pages_are_detached_and_old_files_are_not_rewritten(self):
        self.perceive(0)
        first = self.commit()
        self.assertIsInstance(first, PendingNativeCheckpoint)
        self.assertEqual(len(first.writes), 1)
        self.assertEqual(self.last_commit['native_storage']['new_pages'], 1)
        directory = self.store.root / 'native-pages'
        original = next(directory.glob('*.page'))
        before = original.stat().st_mtime_ns, original.read_bytes()
        self.perceive(1)
        second = self.commit()
        self.assertEqual(len(second.writes), 1)
        self.assertEqual((original.stat().st_mtime_ns, original.read_bytes()), before)
        third = self.commit()
        self.assertFalse(third.writes)
        self.assertEqual(self.last_commit['native_storage']['new_page_bytes'], 0)
        saved = torch.load(self.store.candidates()[0][0], weights_only=True)
        self.assertEqual(saved['format'], 58)
        moments = saved['native']['moments']
        self.assertNotIn('archive', moments)
        self.assertNotIn('page_source', moments)
        self.assertEqual(len(moments['pages']), 2)
        self.assertEqual(len(list(directory.glob('*.page'))), 2)

    def test_capture_avoids_full_archive_serialization_and_detaches_state_from_future_input(self):
        self.perceive(0)
        original = NativeMoments.snapshot
        def selective(memory, pages=None):
            self.assertIsNotNone(pages, 'Runtime capture requested a full SQLite archive.')
            return original(memory, pages=pages)
        with patch.object(NativeMoments, 'snapshot', selective):
            payload = self.store.capture(self.agent)
        clock = self.agent.clock
        self.perceive(1)
        self.store.submit(payload, clock)
        self.assertEqual(self.store.finish()['status'], 'committed')
        agent, mind, _ = load_scheduler(self.store.candidates()[0][0])
        try:
            self.assertEqual(agent.clock, clock)
            self.assertEqual(len(agent.native.moments.traces), 1)
            self.assertFalse(agent.native.names)
        finally:
            close_agent(agent, mind)

    def test_pointer_failure_keeps_previous_state_and_retry_reuses_already_written_pages(self):
        self.perceive(0)
        self.commit()
        before = (self.store.root / 'current.json').read_bytes()
        self.perceive(1)
        with patch('scripts.alice_memory.runtime_store.atomic_json', side_effect=OSError('pointer failure')):
            self.store.submit(self.store.capture(self.agent), self.agent.clock)
            self.assertEqual(self.store.finish()['status'], 'failed')
        self.assertEqual((self.store.root / 'current.json').read_bytes(), before)
        retry = self.store.capture(self.agent)
        self.assertFalse(retry.writes)
        self.store.submit(retry, self.agent.clock)
        self.assertEqual(self.store.finish()['status'], 'committed')
        self.assertEqual(len(self.store.candidates()), 2)

    def test_partial_page_write_failure_does_not_publish_and_can_resume_remaining_pages(self):
        self.commit()
        before = (self.store.root / 'current.json').read_bytes()
        self.perceive(0)
        self.perceive(1)
        writes = []
        def interrupted(path, raw):
            writes.append(path)
            if len(writes) == 2:
                raise OSError('interrupted second page')
            return write_bytes(path, raw)
        with patch('scripts.alice_memory.native_page_store.write_bytes', interrupted):
            self.store.submit(self.store.capture(self.agent), self.agent.clock)
            self.assertEqual(self.store.finish()['status'], 'failed')
        self.assertEqual((self.store.root / 'current.json').read_bytes(), before)
        retry = self.commit()
        self.assertEqual(len(retry.writes), 1)

    def test_corrupt_page_unique_to_current_restores_previous_and_preserves_fallback(self):
        self.perceive(0)
        self.commit()
        first = dict(self.store.manifest['current'])
        self.perceive(1)
        latest = self.commit()
        record = latest.payload['native']['moments']['pages'][1]
        target = page_path(self.store.root / 'native-pages', record)
        raw = target.read_bytes()
        target.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
        agent, mind, recovery = restore_runtime(self.store, None, self.root / 'workers', None)
        try:
            self.assertEqual(len(agent.native.moments.traces), 1)
            self.assertTrue(recovery['recovery_errors'])
            self.store.submit(self.store.capture(agent), agent.clock)
            self.assertEqual(self.store.finish()['status'], 'committed')
            self.assertEqual(self.store.manifest['previous'], first)
            self.assertTrue(target.exists(), 'Corrupt evidence must not be silently overwritten/deleted.')
        finally:
            close_agent(agent, mind)

    def test_missing_shared_page_refuses_both_generations_without_fabricating_memory(self):
        self.perceive(0)
        first = self.commit()
        self.perceive(1)
        self.commit()
        record = first.payload['native']['moments']['pages'][0]
        page_path(self.store.root / 'native-pages', record).unlink()
        with self.assertRaisesRegex(ValueError, 'could not restore'):
            restore_runtime(self.store, None, self.root / 'workers', None)

    def test_disk_budget_failure_preserves_pointer_and_existing_pages(self):
        self.perceive(0)
        self.commit()
        before = (self.store.root / 'current.json').read_bytes()
        self.perceive(1)
        payload = self.store.capture(self.agent)
        with patch('scripts.alice_memory.native_page_store.MAX_BYTES', 1):
            self.store.submit(payload, self.agent.clock)
            self.assertEqual(self.store.finish()['status'], 'failed')
        self.assertEqual((self.store.root / 'current.json').read_bytes(), before)
        self.assertEqual(len(list((self.store.root / 'native-pages').glob('*.page'))), 1)

    def test_references_cannot_select_arbitrary_paths_and_reader_capability_cannot_be_injected(self):
        self.perceive(0)
        first = self.commit()
        for bad in ({'sha256': '../outside', 'size': 100}, {'sha256': '0' * 64, 'size': True}, {'sha256': '0' * 64, 'size': 50001}):
            with self.assertRaises(ValueError):
                page_path(self.store.root / 'native-pages', bad)
        altered = copy.deepcopy(first.payload)
        altered['native']['moments']['page_source'] = str(self.root)
        from scripts.alice_memory.loop_checkpoint import atomic_write
        injected = self.store.root / 'injected.pt'
        atomic_write(injected, altered)
        with self.assertRaisesRegex(ValueError, 'external native checkpoint'):
            load_scheduler(injected)

    def test_foreign_page_directory_and_wrong_owner_are_preserved(self):
        directory = self.store.root / 'native-pages'
        directory.mkdir()
        private = directory / 'private.txt'
        private.write_bytes(b'unrelated')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            self.store.capture(self.agent)
        self.assertEqual(private.read_bytes(), b'unrelated')
        (directory / 'owner.json').write_text(json.dumps({'format': True, 'kind': 'alice-native-weight-pages'}))
        with self.assertRaisesRegex(ValueError, 'ownership'):
            self.store.capture(self.agent)

    def test_portable_export_remains_self_contained_and_external_store_resumes_in_fresh_process(self):
        self.perceive(0)
        self.commit()
        portable = self.root / 'portable.pt'
        save(portable, self.agent)
        exported = torch.load(portable, weights_only=True)
        self.assertEqual(exported['format'], 57)
        self.assertIn('archive', exported['native']['moments'])
        # Move the complete store; references must not contain the old absolute root.
        destination = self.root / 'copied'
        filename = self.store.manifest['current']['file']
        self.store.close()
        shutil.copytree(self.store.root, destination)
        code = """
import sys,torch
from pathlib import Path
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.native_sensor import NativeObservation
from scripts.alice_memory.persistent_runtime import close_agent
for path in sys.argv[1:]:
    agent,mind,_=load_scheduler(Path(path))
    try:
        cue=NativeObservation('image',torch.nn.functional.one_hot(torch.tensor(0),128).float(),1.,0,'0'*64)
        result=agent.native.recall_moments([cue],targets=['audio'])
        assert result['supported'] and result['representations']['audio'].argmax().item()==32
        assert len(agent.native.moments.cache)<=4
        assert 'sentence_transformers' not in sys.modules
    finally:close_agent(agent,mind)
"""
        child = subprocess.run([sys.executable, '-c', code, str(portable), str(destination / filename)], cwd=ROOT, text=True, capture_output=True, timeout=45)
        self.assertEqual(child.returncode, 0, child.stderr)

    def test_finite_runtime_uses_external_pages_and_resumes_without_new_percepts(self):
        self.perceive(0)
        source = self.root / 'source.pt'
        save(source, self.agent)
        runtime = self.root / 'live'
        first = run(runtime, source, seconds=.2, save_every=1.)
        self.assertEqual(first['phase'], 'stopped')
        self.assertEqual(first['native_state']['moments'], 1)
        second = run(runtime, seconds=.2, save_every=1.)
        self.assertTrue(second['recovery']['resumed'])
        self.assertEqual(second['native_state']['moments'], 1)
        self.assertEqual(len(list((runtime / 'native-pages').glob('*.page'))), 1)

    def test_interrupted_empty_page_directory_initialization_can_retry(self):
        with patch('scripts.alice_memory.native_page_store.write_bytes', side_effect=OSError('marker interrupted')):
            with self.assertRaises(OSError):
                self.store.capture(self.agent)
        self.assertFalse(list((self.store.root / 'native-pages').iterdir()))
        self.commit()
        self.assertTrue(self.store.candidates())

    def test_busy_writer_refuses_another_capture_before_detaching_memory(self):
        from concurrent.futures import Future
        self.store.future = Future()
        try:
            with patch.object(NativeMoments, 'snapshot', side_effect=AssertionError('must not copy')):
                with self.assertRaisesRegex(ValueError, 'busy'):
                    self.store.capture(self.agent)
        finally:
            self.store.future = None

    def test_existing_page_corruption_before_commit_is_never_overwritten_or_published(self):
        self.perceive(0)
        first = self.commit()
        before = (self.store.root / 'current.json').read_bytes()
        payload = self.store.capture(self.agent)
        self.assertFalse(payload.writes)
        record = first.payload['native']['moments']['pages'][0]
        path = page_path(self.store.root / 'native-pages', record)
        corrupted = b'!' * record['size']
        path.write_bytes(corrupted)
        self.store.submit(payload, self.agent.clock)
        self.assertEqual(self.store.finish()['status'], 'failed')
        self.assertEqual((self.store.root / 'current.json').read_bytes(), before)
        self.assertEqual(path.read_bytes(), corrupted)

    def test_self_consistent_hash_of_unreadable_page_still_recovers_previous(self):
        from scripts.alice_memory.loop_checkpoint import atomic_write
        from scripts.alice_memory.runtime_store import atomic_json, digest
        self.perceive(0)
        self.commit()
        self.perceive(1)
        self.commit()
        current = self.store.manifest['current']
        path = self.store.path(current['file'])
        payload = torch.load(path, weights_only=True)
        raw = b'not a safe torch weight archive'
        record = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
        page_path(self.store.root / 'native-pages', record).write_bytes(raw)
        payload['native']['moments']['pages'][1] = record
        atomic_write(path, payload)
        current.update(size=path.stat().st_size, sha256=digest(path))
        atomic_json(self.store.root / 'current.json', self.store.manifest)
        agent, mind, recovery = restore_runtime(self.store, None, self.root / 'workers', None)
        try:
            self.assertEqual(len(agent.native.moments.traces), 1)
            self.assertTrue(recovery['recovery_errors'])
        finally:
            close_agent(agent, mind)

    def test_page_read_is_bounded_even_if_file_grows_after_size_check(self):
        from scripts.alice_memory.native_page_store import read_page
        from types import SimpleNamespace
        stream = io.BytesIO(b'x' * 1000000)
        class GrownPath:
            def stat(self):
                return SimpleNamespace(st_size=10)
            def open(self, mode):
                return stream
        with patch('scripts.alice_memory.native_page_store.page_path', return_value=GrownPath()):
            with patch.object(stream, 'close'):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    read_page(self.store.root, {'sha256': '0' * 64, 'size': 10})
                self.assertEqual(stream.tell(), 11)


if __name__ == '__main__':
    unittest.main()
