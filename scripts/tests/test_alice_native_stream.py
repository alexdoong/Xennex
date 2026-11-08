"""Native stream ownership, durable release, process slots and restart contracts."""
import copy
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.conceptual_mind import ConceptualMind, save, restore
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.language_coordinator import LanguageCoordinator
from scripts.alice_memory.language_process import LanguageProcess
from scripts.alice_memory.native_inbox import NativeInbox
from scripts.alice_memory.native_process import NativeProcess
from scripts.alice_memory.persistent_runtime import close_agent, run
from scripts.alice_memory.runtime_snapshot import capture
from scripts.alice_memory.runtime_store import RuntimeStore
import test_alice_word_grounding as fixtures

COMMIT = {'file': 'alice-' + 'a' * 32 + '.pt', 'sha256': 'b' * 64,
          'previous_file': 'alice-' + 'c' * 32 + '.pt', 'previous_sha256': 'd' * 64}


class InboxContracts(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=ROOT / 'bin')
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.signal = self.folder / 'signal.png'
        Image.new('RGB', (224, 224), 'red').save(self.signal)
        self.inbox = NativeInbox(self.folder / 'inbox')

    def job(self):
        frame = self.inbox.publish({'image': self.signal}, 'nivo')
        return {'frame': frame, 'manifest': self.inbox.read(frame), 'source_sequence': 0,
                'status': 'completed', 'result': {'encoded': 1}, 'error': None}

    def test_publication_is_atomic_bounded_and_preserves_original_file(self):
        job = self.job()
        self.assertEqual(self.inbox.available(-1), [job['frame']])
        self.assertTrue(self.signal.exists())
        self.assertEqual(job['manifest']['name'], 'nivo')
        with self.assertRaises(ValueError):
            self.inbox.publish({'image': self.signal}, 'nivo', 'self')
        with self.assertRaises(ValueError):
            self.inbox.publish({'unsupported': self.signal})

    def test_mirage_import_converts_geometry_but_never_teaches_generated_names(self):
        import hashlib
        scene = {'image_sha256': hashlib.sha256(self.signal.read_bytes()).hexdigest(), 'result': {'objects': [
            {'bbox': [500, 0, 1000, 1000], 'score': .4, 'name': 'nome inventado'},
            {'bbox': [0, 250, 500, 750], 'score': .8, 'id': 13},
            {'bbox': [0, 250, 500, 750], 'score': .7, 'id': 14},
        ], 'text': [{'string': 'irrelevant'}]}}
        frame = self.inbox.publish({'image': self.signal}, mirage_result=scene)
        manifest = self.inbox.read(frame)
        self.assertIsNone(manifest['name'])
        self.assertEqual(manifest['image_regions'], [[0, 56, 112, 168], [112, 0, 224, 224]])
        changed = {**scene, 'image_sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self.inbox.publish({'image': self.signal}, mirage_result=changed)
        self.assertEqual([path.name for path in (self.inbox.root / 'frames').iterdir()], [frame])

    def test_receipt_releases_only_owned_copies_and_repeating_ack_is_safe(self):
        job = self.job()
        self.inbox.acknowledge(job, COMMIT)
        self.assertFalse(self.inbox.frame_path(job['frame']).exists())
        self.assertTrue(self.signal.exists())
        self.inbox.acknowledge(job, COMMIT)
        receipt = json.loads((self.inbox.root / 'receipts' / 'frame-0000000.json').read_text())
        self.assertEqual(receipt['commit_sha256'], COMMIT['sha256'])

    def test_interrupted_cleanup_finishes_from_the_committed_receipt(self):
        job = self.job()
        target = self.inbox.frame_path(job['frame']) / job['manifest']['files'][0]['file']
        original = Path.unlink
        def fail(path, *args, **kwargs):
            if path == target:
                raise OSError('interrupted copy cleanup')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail):
            with self.assertRaises(OSError):
                self.inbox.acknowledge(job, COMMIT)
        self.inbox.acknowledge(job, COMMIT)
        self.assertFalse(self.inbox.frame_path(job['frame']).exists())

    def test_private_or_changed_files_are_preserved_and_unknown_directories_not_claimed(self):
        job = self.job()
        private = self.inbox.frame_path(job['frame']) / 'private.txt'
        private.write_text('preserve me')
        with self.assertRaises(ValueError):
            self.inbox.acknowledge(job, COMMIT)
        self.assertEqual(private.read_text(), 'preserve me')
        other = self.folder / 'unrelated'
        other.mkdir()
        (other / 'private.txt').write_text('preserve')
        with self.assertRaises(ValueError):
            NativeInbox(other)
        self.assertEqual({p.name for p in other.iterdir()}, {'private.txt'})
        with self.assertRaises(ValueError):
            self.inbox.frame_path('../other')


class StreamContracts(unittest.TestCase):
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
        self.signal = self.folder / 'signal.png'
        Image.new('RGB', (224, 224), 'red').save(self.signal)
        self.inbox = NativeInbox(self.folder / 'inbox')
        self.config = self.folder / 'native.json'
        self.config.write_text(json.dumps({'delay': .25}))
        self.language_config = self.folder / 'language.json'
        self.language_config.write_text(json.dumps({'delay': .25}))
        self.workers = []
        self.mirage_folder = None
        self.memory_patch = patch('scripts.alice_memory.native_process.physical_memory',
                                  return_value={'used_bytes': 1, 'total_bytes': 100})
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)

    def factory(self, jobs):
        self.assertFalse(any(worker.process.poll() is None for worker in self.workers))
        worker = NativeProcess(jobs, self.inbox, self.folder / 'workers', self.folder, sys.executable,
                               module='scripts.tests.alice_fake_native_worker',
                               environment={'ALICE_FAKE_NATIVE_CONFIG': str(self.config)}, mirage_folder=self.mirage_folder)
        self.workers.append(worker)
        return worker

    def language_factory(self, operation):
        self.assertFalse(any(worker.process.poll() is None for worker in self.workers))
        worker = LanguageProcess(operation, self.folder / 'workers', 10., 'scripts.tests.alice_fake_language_worker',
                                 {'ALICE_FAKE_LANGUAGE_CONFIG': str(self.language_config)})
        self.workers.append(worker)
        return worker

    def core(self, language=False):
        grounded = self.fixture.fixture(False)
        base = LanguageCoordinator(grounded, 'http://127.0.0.1:11438', 'fixture', self.folder / 'workers', self.language_factory) if language else grounded
        agent = ConceptualMind(base)
        self.addCleanup(agent.close)
        agent.native_stream.configure(self.inbox, self.factory)
        return agent

    def submit(self, agent, name='nivo'):
        frame = self.inbox.publish({'image': self.signal}, name)
        manifest = self.inbox.read(frame)
        self.assertTrue(agent.native_stream.ingest(frame, manifest, time.time()))
        return max(agent.native_stream.jobs)

    def until(self, agent, predicate):
        deadline = time.monotonic() + 25.
        while not predicate():
            self.assertLess(time.monotonic(), deadline)
            agent.tick(.05)
            time.sleep(.02)

    def finished(self, agent, number):
        return agent.native_stream.jobs[number]['status'] in ('completed', 'ignored', 'failed')

    def test_visual_regions_cross_process_and_restore_from_durable_page_checkpoint(self):
        agent = self.core()
        boxes = [[10, 12, 90, 80]]
        frame = self.inbox.publish({'image': self.signal}, image_regions=boxes)
        self.assertTrue(agent.native_stream.ingest(frame, self.inbox.read(frame), time.time()))
        number = max(agent.native_stream.jobs)
        self.until(agent, lambda: self.finished(agent, number))
        job = agent.native_stream.jobs[number]
        self.assertEqual(job['status'], 'completed', job['error'])
        self.assertEqual(job['result']['region_count'], 1)
        index = job['moment_ref']['id']
        store = RuntimeStore(self.folder / 'runtime')
        self.addCleanup(store.close)
        self.assertTrue(store.submit(store.capture(agent), agent.clock))
        self.assertEqual(store.finish()['status'], 'committed')
        restored, mind, _ = load_scheduler(store.candidates()[0][0])
        self.addCleanup(close_agent, restored, mind)
        self.assertEqual(restored.native.moments.regions[index]['boxes'], boxes)
        self.assertTrue(torch.equal(restored.native.moments.regions[index]['routes'],
                                    agent.native.moments.regions[index]['routes']))

    def test_changed_region_worker_receipt_cannot_create_a_moment(self):
        agent = self.core()
        self.config.write_text(json.dumps({'mode': 'changed_region_box'}))
        frame = self.inbox.publish({'image': self.signal}, image_regions=[[10, 12, 90, 80]])
        self.assertTrue(agent.native_stream.ingest(frame, self.inbox.read(frame), time.time()))
        number = max(agent.native_stream.jobs)
        self.until(agent, lambda: self.finished(agent, number))
        job = agent.native_stream.jobs[number]
        self.assertEqual(job['status'], 'failed')
        self.assertIn('changed the requested boxes', job['error'])
        self.assertEqual(agent.native.moments.next_id, 0)

    def test_sound_to_visual_name_in_receipt_keeps_the_two_sensory_sources_separate(self):
        import wave
        from scripts.alice_memory.concept_query_language import sha
        from scripts.alice_memory.native_stream import restore as restore_stream
        agent = self.core()
        agent.native.configure_implicit_recall(True)
        wave_path = self.folder / 'sound.wav'
        with wave.open(str(wave_path), 'wb') as stream:
            stream.setparams((1, 2, 16000, 160, 'NONE', 'not compressed'))
            stream.writeframes(b'\0' * 320)
        frame = self.inbox.publish({'image': self.signal, 'audio': wave_path})
        self.assertTrue(agent.native_stream.ingest(frame, self.inbox.read(frame), time.time()))
        first = max(agent.native_stream.jobs)
        self.until(agent, lambda: self.finished(agent, first))
        ref = agent.native_stream.jobs[first]['moment_ref']
        result = agent.native.teach_retained_name('maruvi', ref, 'image', 'person', agent.clock,
            {'kind': 'external_word_reply', 'reply_sha256': sha('maruvi'), 'request_sha256': sha('Qual nome?')})
        self.assertTrue(result['learned'])
        frame = self.inbox.publish({'audio': wave_path})
        self.assertTrue(agent.native_stream.ingest(frame, self.inbox.read(frame), time.time()))
        second = max(agent.native_stream.jobs)
        self.until(agent, lambda: self.finished(agent, second))
        job = agent.native_stream.jobs[second]
        self.assertFalse(job['result']['recognized'][0]['supported'])
        self.assertEqual(job['result']['audio_association']['name'], 'maruvi')
        self.assertEqual(job['result']['audio_association']['sources'], [ref])
        saved = agent.native_stream.snapshot()
        self.assertEqual(restore_stream(saved, agent).jobs[second], job)
        saved['jobs'][-1]['result']['audio_association']['sources'] = [job['moment_ref']]
        with self.assertRaises(ValueError):
            restore_stream(saved, agent)

    def test_word_audio_is_explicit_and_survives_a_paged_checkpoint(self):
        import wave
        agent = self.core()
        wave_path = self.folder / 'word.wav'
        with wave.open(str(wave_path), 'wb') as stream:
            stream.setparams((1, 2, 16000, 160, 'NONE', 'not compressed'))
            stream.writeframes(b'\0' * 320)
        with self.assertRaises(ValueError):
            self.inbox.publish({'audio': wave_path}, 'chuva', origin='environment', word_audio=True)
        for name, status in (('chuva', 'learned'), (None, 'heard')):
            frame = self.inbox.publish({'audio': wave_path}, name, word_audio=True)
            self.assertTrue(agent.native_stream.ingest(frame, self.inbox.read(frame), time.time()))
            index = max(agent.native_stream.jobs)
            self.until(agent, lambda: self.finished(agent, index))
            job = agent.native_stream.jobs[index]
            self.assertEqual(job['status'], 'completed', job['error'])
            self.assertEqual(job['result']['pronunciation']['status'], status)
            self.assertEqual(job['result']['pronunciation']['word'], 'chuva')
            self.assertIsNone(job['result']['learning'])
        store = RuntimeStore(self.folder / 'runtime')
        self.addCleanup(store.close)
        self.assertTrue(store.submit(store.capture(agent), agent.clock))
        self.assertEqual(store.finish()['status'], 'committed')
        reopened, mind, _ = load_scheduler(store.candidates()[0][0])
        self.addCleanup(close_agent, reopened, mind)
        self.assertEqual(reopened.native.moments.pronunciations[0]['word'], 'chuva')
        self.assertEqual(reopened.native.names, [])
        self.assertEqual(reopened.native_stream.jobs[index]['result']['pronunciation'], job['result']['pronunciation'])

    def test_automatic_regions_and_detector_error_preserve_two_full_scenes(self):
        self.mirage_folder = self.folder
        agent = self.core()
        first = self.submit(agent, name=None)
        self.until(agent, lambda: self.finished(agent, first))
        self.config.write_text(json.dumps({'automatic_result': 'detector_error'}))
        second = self.submit(agent, name=None)
        self.until(agent, lambda: self.finished(agent, second))
        jobs = [agent.native_stream.jobs[number] for number in (first, second)]
        self.assertEqual([job['status'] for job in jobs], ['completed', 'completed'])
        self.assertEqual([job['result']['region_status'] for job in jobs], ['detected', 'detector_error'])
        self.assertEqual([job['result']['region_count'] for job in jobs], [1, 0])
        store = RuntimeStore(self.folder / 'runtime')
        self.addCleanup(store.close)
        self.assertTrue(store.submit(store.capture(agent), agent.clock))
        self.assertEqual(store.finish()['status'], 'committed')
        restored, mind, _ = load_scheduler(store.candidates()[0][0])
        self.addCleanup(close_agent, restored, mind)
        self.assertEqual(restored.native.moments.next_id, 2)
        self.assertEqual(list(restored.native.moments.regions), [jobs[0]['moment_ref']['id']])

    def test_shared_slot_continues_ticks_and_external_frame_teaches_once(self):
        agent = self.core(True)
        before = agent.temporal.observations
        agent.submit('O que aconteceu?')
        number = self.submit(agent)
        initial = agent.clock
        self.until(agent, lambda: self.finished(agent, number))
        self.assertEqual(agent.native_stream.jobs[number]['status'], 'completed')
        self.assertGreater(agent.clock, initial)
        self.assertEqual(len(agent.native.sources), 1)
        self.assertEqual(agent.temporal.observations, before)
        self.assertIsNone(agent.agent.external_worker_owner)
        job = agent.native_stream.jobs[number]
        self.assertFalse(agent.native_stream.ingest(job['frame'], job['manifest'], time.time()))

    def test_pending_process_and_completion_survive_restart_without_a_second_update(self):
        agent = self.core()
        number = self.submit(agent)
        agent.tick(.05)
        self.assertEqual(agent.native_stream.jobs[number]['status'], 'encoding')
        checkpoint = self.folder / 'pending.pt'
        save(checkpoint, agent)
        agent.close()
        resumed, mind, _ = load_scheduler(checkpoint)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.native_stream.configure(self.inbox, self.factory)
        self.assertEqual(resumed.native_stream.jobs[number]['status'], 'waiting')
        self.until(resumed, lambda: self.finished(resumed, number))
        save(checkpoint, resumed)
        resumed.close()
        final, final_mind, _ = load_scheduler(checkpoint)
        self.addCleanup(lambda: close_agent(final, final_mind))
        self.assertEqual(len(final.native.sources), 1)
        final.tick(.1)
        self.assertEqual(len(final.native.sources), 1)
        self.assertEqual(final.native_stream.jobs[number]['status'], 'completed')

    def test_corrupt_receipt_does_not_change_the_native_mind(self):
        for mode in ('changed_hash', 'changed_source'):
            self.config.write_text(json.dumps({'delay': .1, 'mode': mode}))
            agent = self.core()
            number = self.submit(agent)
            self.until(agent, lambda: self.finished(agent, number))
            self.assertEqual(agent.native_stream.jobs[number]['status'], 'failed')
            self.assertEqual(agent.native.observations, 0)
            self.assertFalse(agent.native.sources)
            agent.close()

    def test_admission_deferral_preserves_copy_then_resumes_without_fabricating_perception(self):
        self.config.write_text(json.dumps({'delay': .1, 'mode': 'deferred'}))
        agent = self.core()
        number = self.submit(agent)
        self.until(agent, lambda: agent.native_stream.jobs[number]['deferrals'] == 1)
        self.assertEqual(agent.native.observations, 0)
        self.assertTrue(self.inbox.frame_path(agent.native_stream.jobs[number]['frame']).exists())
        self.config.write_text(json.dumps({'delay': .1}))
        self.until(agent, lambda: self.finished(agent, number))
        self.assertEqual(len(agent.native.sources), 1)

    def test_failed_commit_keeps_copy_and_successful_commit_releases_it(self):
        agent = self.core()
        number = self.submit(agent)
        self.until(agent, lambda: self.finished(agent, number))
        job = copy.deepcopy(agent.native_stream.jobs[number])
        with RuntimeStore(self.folder / 'store') as store:
            with patch.object(store, 'commit', side_effect=OSError('disk failure')):
                store.submit(capture(agent), agent.clock)
                self.assertEqual(store.finish()['status'], 'failed')
            self.assertTrue(self.inbox.frame_path(job['frame']).exists())
            store.submit(capture(agent), agent.clock)
            event = store.finish()
            self.assertEqual(event['status'], 'committed')
            agent.native_stream.committed([number], event['record'])
            self.assertTrue(self.inbox.frame_path(job['frame']).exists())
            store.submit(capture(agent), agent.clock)
            second = store.finish()
            agent.native_stream.committed([number], second['record'], event['record'])
            self.assertFalse(self.inbox.frame_path(job['frame']).exists())
            # The committed generation still has the terminal job; recovery
            # acknowledges it again rather than replaying the lesson.
            recovered, mind, _ = load_scheduler(store.candidates()[0][0])
            self.addCleanup(lambda: close_agent(recovered, mind))
            recovered.native_stream.configure(self.inbox, self.factory)
            recovered.native_stream.committed([number], second['record'], event['record'])
            self.assertEqual(len(recovered.native.sources), 1)

    def test_saved_stream_rejects_false_learning_time_and_source_identity(self):
        agent = self.core()
        number = self.submit(agent)
        self.until(agent, lambda: self.finished(agent, number))
        original = agent.snapshot()
        for field, value in (('acquired_at', agent.clock + 1.), ('source_sequence', 99), ('status', 'waiting')):
            damaged = copy.deepcopy(original)
            damaged['native_stream']['jobs'][0][field] = value
            with self.assertRaises(ValueError):
                restore(damaged)

    def test_runtime_consumes_published_input_and_restarts_after_durable_ack(self):
        agent = self.core()
        checkpoint = self.folder / 'initial.pt'
        save(checkpoint, agent)
        self.inbox.publish({'image': self.signal}, 'nivo')
        first = run(self.folder / 'runtime', checkpoint, seconds=.3, save_every=1., native_inbox=self.inbox.root,
                    native_backend='fixture', native_ram_fraction=.9)
        self.assertEqual(first['phase'], 'stopped')
        self.assertTrue(first['native_workers_terminal'])
        self.assertEqual(first['native_state']['lessons'], 0)
        self.assertEqual(len(list((self.inbox.root / 'frames').iterdir())), 1)
        # Force completion between regular saves: shutdown must create both
        # durable generations before releasing the owned input copy.
        second = run(self.folder / 'runtime', seconds=8., save_every=3600., native_inbox=self.inbox.root,
                     native_backend='fixture', native_ram_fraction=.9)
        self.assertEqual(second['native_state']['lessons'], 1)
        self.assertEqual(second['native_state']['observations'], 1)
        self.assertEqual(len(list((self.inbox.root / 'frames').iterdir())), 0)
        self.assertTrue(second['recovery']['resumed'])
        self.assertFalse(second['native_inbox_errors'])

    def test_two_completed_generations_allow_corrupt_current_fallback_after_copy_release(self):
        agent = self.core()
        number = self.submit(agent)
        self.until(agent, lambda: self.finished(agent, number))
        with RuntimeStore(self.folder / 'store') as store:
            store.submit(capture(agent), agent.clock)
            first = store.finish()
            agent.native_stream.committed([number], first['record'])
            self.assertTrue(self.inbox.frame_path(agent.native_stream.jobs[number]['frame']).exists())
            store.submit(capture(agent), agent.clock)
            second = store.finish()
            agent.native_stream.committed([number], second['record'], first['record'])
            store.path(second['record']['file']).write_bytes(b'corrupt current')
            candidates = store.candidates()
            self.assertEqual(len(candidates), 1)
            restored, mind, _ = load_scheduler(candidates[0][0])
            self.addCleanup(lambda: close_agent(restored, mind))
            self.assertEqual(len(restored.native.sources), 1)
            self.assertEqual(restored.native_stream.jobs[number]['status'], 'completed')

    def test_already_captured_frame_survives_long_offline_gap_without_invented_input(self):
        agent = self.core()
        number = self.submit(agent)
        acquired = agent.native_stream.jobs[number]['acquired_at']
        checkpoint = self.folder / 'offline.pt'
        save(checkpoint, agent)
        agent.close()
        resumed, mind, _ = load_scheduler(checkpoint)
        self.addCleanup(lambda: close_agent(resumed, mind))
        resumed.unobserved_gap(600.)
        resumed.tick(0.)
        self.assertEqual(resumed.native.observations, 0)
        resumed.native_stream.configure(self.inbox, self.factory)
        self.until(resumed, lambda: self.finished(resumed, number))
        self.assertEqual(resumed.native_stream.jobs[number]['status'], 'completed')
        self.assertEqual(len(resumed.native.sources), 1)
        self.assertEqual(resumed.native.sources[0]['acquired_at'], acquired)

    def test_unbounded_runtime_does_not_inherit_temporary_ninety_percent_override(self):
        with self.assertRaises(ValueError):
            run(self.folder / 'runtime', native_ram_fraction=.9)


if __name__ == '__main__':
    unittest.main()
