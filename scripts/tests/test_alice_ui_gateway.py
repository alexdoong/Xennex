"""Panel bridge preserves learned state, transport identity and selected files."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alice_memory.ui_gateway import prepare, execute
from scripts.alice_memory.conceptual_mind import save
from scripts.alice_memory.interaction_inbox import InteractionInbox, atomic
from scripts.alice_memory.native_inbox import NativeInbox
from scripts.alice_memory.runtime_store import RuntimeLease
from scripts.alice_memory.continuous_experiment import load_scheduler
from scripts.alice_memory.persistent_runtime import close_agent
import test_alice_native_name as names
import test_alice_interactions as interactions
import test_alice_word_grounding as fixtures


class GatewayContracts(unittest.TestCase):
    setUp = names.NameLifecycleContracts.setUp
    configure = names.NameLifecycleContracts.configure
    factory = names.NameLifecycleContracts.factory
    core = names.NameLifecycleContracts.core
    frame = names.NameLifecycleContracts.frame
    until = names.NameLifecycleContracts.until
    setUpClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.setUpClass())
    tearDownClass = classmethod(lambda cls: fixtures.WrittenGroundingTests.tearDownClass())

    def source(self):
        core = self.core(False)
        inbox = interactions.InteractionOwnerContracts.inbox(self, core)
        identifier, _ = interactions.InteractionOwnerContracts.ingest(self, core, inbox, 'name',
            {'text': 'Essa imagem se chama lumo.', 'focus': 'image', 'moment': 0, 'frame': None})
        self.until(core, lambda: core.interactions.records[identifier]['status'] == 'completed')
        checkpoint = self.folder / 'source.pt'
        save(checkpoint, core)
        return core, checkpoint, identifier

    def test_prepared_copy_preserves_memory_and_interaction_identity_without_source_write(self):
        core, source, identifier = self.source()
        checksum = hashlib.sha256(source.read_bytes()).hexdigest()
        root = self.folder / 'panel'
        self.assertEqual(prepare(root, source), {'resumed': False})
        copied, mind, _ = load_scheduler(root / 'seed.pt', self.folder / 'verify', self.factory)
        self.addCleanup(lambda: close_agent(copied, mind))
        self.assertEqual(copied.native.names, core.native.names)
        self.assertEqual(copied.interactions.records[identifier]['status'], 'completed')
        inbox = InteractionInbox(root / 'human')
        self.assertEqual(inbox.stream_id, core.interactions.stream_id)
        result = execute(root, {'action': 'send', 'kind': 'meaning', 'payload': {'text': 'O que é lumo?'}})
        request = inbox.request(inbox.available()[0])
        self.assertEqual(result['id'], request['id'])
        self.assertEqual(request['sequence'], core.interactions.last_sequence + 1)
        self.assertEqual(prepare(root, self.folder / 'missing.pt'), {'resumed': False})
        self.assertEqual(len(inbox.available()), 1)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), checksum)

    def test_selected_text_is_copied_and_source_unchanged(self):
        _, source, _ = self.source()
        root = self.folder / 'panel'
        prepare(root, source)
        text = self.folder / 'experience.txt'
        text.write_text('Formigas e abelhas.', encoding='utf-8')
        result = execute(root, {'action': 'perceive', 'modality': 'text', 'path': str(text)})
        inbox = NativeInbox(root / 'sensory')
        self.assertEqual(result['stream_id'], inbox.stream_id)
        self.assertEqual(result['sequence'], 0)
        self.assertEqual(result['label'], 'experience.txt')
        self.assertEqual(text.read_text(encoding='utf-8'), 'Formigas e abelhas.')
        self.assertEqual(len(inbox.available(-1)), 1)

    def test_selected_png_and_wav_publish_one_experience(self):
        _, source, _ = self.source()
        root = self.folder / 'panel'
        prepare(root, source)
        image, sound = self.folder / 'object.png', self.folder / 'object.wav'
        image.write_bytes(b'image fixture')
        sound.write_bytes(b'wave fixture')
        with self.assertRaises(ValueError):
            execute(root, {'action': 'perceive_pair', 'image': str(image), 'audio': ''})
        result = execute(root, {'action': 'perceive_pair', 'image': str(image), 'audio': str(sound)})
        inbox = NativeInbox(root / 'sensory')
        frame, = inbox.available(-1)
        manifest = inbox.read(frame)
        self.assertEqual(result, {'stream_id': inbox.stream_id, 'sequence': 0,
                                  'label': 'object.png + object.wav', 'modality': 'image_audio'})
        self.assertEqual([item['modality'] for item in manifest['files']], ['image', 'audio'])
        self.assertEqual(image.read_bytes(), b'image fixture')
        self.assertEqual(sound.read_bytes(), b'wave fixture')

    def test_pronunciation_publication_distinguishes_lesson_from_query(self):
        _, source, _ = self.source()
        root = self.folder / 'panel'
        prepare(root, source)
        sound = self.folder / 'speech.wav'
        sound.write_bytes(b'wave fixture')
        for word in ('Água', None):
            execute(root, {'action': 'word_audio', 'word': word, 'path': str(sound)})
        inbox = NativeInbox(root / 'sensory')
        received = [inbox.read(frame) for frame in inbox.available(-1)]
        self.assertEqual([item['name'] for item in received], ['água', None])
        self.assertTrue(all(item['word_audio'] and item['format'] == 3 for item in received))

    def test_existing_partial_inbox_and_foreign_runtime_are_preserved(self):
        root = self.folder / 'partial'
        inbox = InteractionInbox(root / 'human')
        identifier = inbox.publish('ask', {'text': 'Oi?'})
        with self.assertRaises(ValueError): prepare(root, self.folder / 'unused.pt')
        self.assertEqual(inbox.request(inbox.available()[0])['id'], identifier)
        other = self.folder / 'locked'
        with RuntimeLease(other / 'runtime'):
            with self.assertRaises(OSError): prepare(other, self.folder / 'unused.pt')
        self.assertFalse((other / 'seed.pt').exists())

    def test_gateway_errors_and_message_path_do_not_load_torch(self):
        root = self.folder / 'rpc'
        root.mkdir()
        (root / 'seed.pt').write_bytes(b'placeholder-not-opened-by-message')
        code = "import sys,json;from scripts.alice_memory.ui_gateway import execute;execute(sys.argv[1],{'action':'send','kind':'ask','payload':{'text':'Oi?'}});assert 'torch' not in sys.modules"
        child = subprocess.run([sys.executable, '-c', code, str(root)], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(child.returncode, 0, child.stderr)
        for raw in ('not-json', json.dumps({'action': 'send', 'kind': 'ask', 'payload': {'text': 'Oi?'}, 'execute': 'arbitrary'}), 'x' * 32769):
            child = subprocess.run([sys.executable, '-m', 'scripts.alice_memory.ui_gateway', '--root', str(root)],
                input=raw, cwd=ROOT, capture_output=True, text=True, timeout=20)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertFalse(json.loads(child.stdout)['ok'])
        with self.assertRaises(ValueError): execute(self.folder / 'unprepared', {'action': 'send', 'kind': 'ask', 'payload': {'text': 'Oi?'}})

    def test_native_transport_identity_and_counter_survive_the_copy(self):
        core = self.core(False)
        core.native_stream.stream_id = 'b' * 32
        core.native_stream.last_source_sequence = 9
        source = self.folder / 'bound-source.pt'
        save(source, core)
        root = self.folder / 'panel'
        prepare(root, source)
        text = self.folder / 'input.txt'
        text.write_text('Um som e uma imagem.', encoding='utf-8')
        value = execute(root, {'action': 'perceive', 'modality': 'text', 'path': str(text)})
        self.assertEqual(value['stream_id'], 'b' * 32)
        self.assertEqual(value['sequence'], 10)


if __name__ == '__main__':
    unittest.main()
