"""Menú Configuración: listado de modelos de Ollama y guardado del elegido.

Ollama se simula: no hace falta el servicio ni modelos descargados.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import build


def entry(name, family='llama', size=4e9, remote=None):
    return SimpleNamespace(model=name, size=size, remote_host=remote,
                           details=SimpleNamespace(family=family))


FAKE_MODELS = [
    entry('gemma3:4b', 'gemma3'),
    entry('qwen3-embedding:0.6b', 'qwen3'),
    entry('nomic-embed-text:latest', 'nomic-bert'),
    entry('gpt-oss:20b-cloud', 'gptoss', size=0, remote='https://ollama.com:443'),
    entry('deepseek-v3.1:671b-cloud', 'deepseek2', size=0),
]
FAKE_CAPS = {
    'gemma3:4b': ['completion', 'vision'],
    'qwen3-embedding:0.6b': ['embedding'],
    'nomic-embed-text:latest': None,          # Ollama antiguo: sin capacidades
    'gpt-oss:20b-cloud': ['completion', 'tools', 'thinking'],
    'deepseek-v3.1:671b-cloud': ['completion', 'tools', 'thinking'],
}


FAKE_CLOUD = [
    {'name': build.cloud_local_name(n), 'cloud': True, 'thinking': t, 'vision': False,
     'size': 0, 'date': d}
    for n, t, d in [('glm-5.3', True, '2026-08-28'), ('kimi-k2.6', True, '2026-04-20'),
                    ('gpt-oss:20b', True, '2025-08-05'), ('plain-model', False, '2025-01-01')]
]


class FakeOllama:
    def list(self):
        return SimpleNamespace(models=FAKE_MODELS)

    def show(self, name):
        return SimpleNamespace(capabilities=FAKE_CAPS[name])


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [
            patch.object(build, 'ollama', FakeOllama(), create=True),
            patch.object(build, 'OLLAMA_AVAILABLE', True),
            patch.object(build, 'SETTINGS_FILE', Path(self.tmp.name) / 'settings.json'),
            patch.object(build, 'OLLAMA_MODEL', build.DEFAULT_OLLAMA_MODEL),
            patch.object(build, 'OLLAMA_SUPPORTS_THINK', True),
            # El catalogo real de la nube no se consulta en las pruebas.
            patch.object(build, 'list_cloud_models', return_value=list(FAKE_CLOUD)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_lists_only_llms_including_cloud(self):
        models = build.list_llm_models()
        names = [m['name'] for m in models]
        self.assertEqual(names, ['gemma3:4b', 'deepseek-v3.1:671b-cloud', 'gpt-oss:20b-cloud'])
        cloud = {m['name']: m['cloud'] for m in models}
        self.assertFalse(cloud['gemma3:4b'])
        self.assertTrue(cloud['gpt-oss:20b-cloud'] and cloud['deepseek-v3.1:671b-cloud'])

    def test_choosing_a_model_saves_it_and_its_thinking_support(self):
        settings = {}
        with patch('builtins.input', return_value='1'):
            build.configure_model(settings)
        saved = json.loads(build.SETTINGS_FILE.read_text(encoding='utf-8'))
        self.assertEqual(saved, {'ollama_model': 'gemma3:4b', 'ollama_thinking': False})
        self.assertEqual(build.OLLAMA_MODEL, 'gemma3:4b')
        self.assertEqual(build.model_slug(), 'gemma3-4b')
        # gemma3 no razona: `think` no se envia.
        self.assertIsNone(build._think_arg('low'))

    def test_enter_keeps_current_model(self):
        with patch('builtins.input', return_value=''):
            build.configure_model({})
        self.assertFalse(build.SETTINGS_FILE.exists())
        self.assertEqual(build.OLLAMA_MODEL, build.DEFAULT_OLLAMA_MODEL)

    def test_ollama_down_is_reported_not_raised(self):
        class Down:
            def list(self):
                raise ConnectionError('Failed to connect to Ollama')
        with patch.object(build, 'ollama', Down()), patch('builtins.input', return_value='1'):
            build.configure_model({})
        self.assertFalse(build.SETTINGS_FILE.exists())

    def test_menu_returns_to_main_menu(self):
        answers = iter(['3', '0', '2'])
        with patch('builtins.input', lambda *_: next(answers)):
            self.assertEqual(build.choose_mode(), 'config')
            build.run_config()
            self.assertEqual(build.choose_mode(), 'pdf')


class CloudTests(ConfigTests):
    def test_catalog_names_become_local_tags(self):
        self.assertEqual(build.cloud_local_name('gpt-oss:20b'), 'gpt-oss:20b-cloud')
        self.assertEqual(build.cloud_local_name('kimi-k2.6'), 'kimi-k2.6:cloud')
        self.assertEqual(build.cloud_local_name('kimi-k2.6:cloud'), 'kimi-k2.6:cloud')

    def test_catalog_filters_non_llms_and_sorts_newest_first(self):
        catalog = {'models': [
            {'name': 'old', 'model': 'old', 'modified_at': '2025-01-01T00:00:00Z', 'size': 1,
             'capabilities': ['completion']},
            {'name': 'clef:27b', 'model': 'clef:27b', 'modified_at': '2026-10-04T00:00:00Z',
             'capabilities': ['decision', 'vision']},
            {'name': 'new', 'model': 'new', 'modified_at': '2026-11-04T00:00:00Z', 'size': 0,
             'capabilities': ['completion', 'thinking']},
        ]}
        import io, json as _json
        fake = io.BytesIO(_json.dumps(catalog).encode())
        fake.__enter__ = lambda *a: fake
        fake.__exit__ = lambda *a: None
        self.patches[-1].stop()          # usar la funcion real
        try:
            with patch('urllib.request.urlopen', return_value=fake):
                models = build.list_cloud_models()
        finally:
            self.patches[-1].start()
        self.assertEqual([m['name'] for m in models], ['new:cloud', 'old:cloud'])
        self.assertTrue(models[0]['thinking'])

    def test_filter_then_pick_cloud_model(self):
        # 2 = Nube; 'kimi' filtra; 1 = primer resultado del filtro.
        answers = iter(['2', 'kimi', '1'])
        with patch('builtins.input', lambda *_: next(answers)):
            build.configure_model({})
        saved = json.loads(build.SETTINGS_FILE.read_text(encoding='utf-8'))
        self.assertEqual(saved, {'ollama_model': 'kimi-k2.6:cloud', 'ollama_thinking': True})

    def test_paging_wraps_and_enter_returns(self):
        answers = iter(['2', 'm', 'm', ''])
        with patch.object(build, 'CLOUD_PAGE_SIZE', 2), patch('builtins.input', lambda *_: next(answers)):
            build.configure_model({})
        self.assertFalse(build.SETTINGS_FILE.exists())

    def test_preflight_explains_missing_credits(self):
        class NoCredits:
            def chat(self, **kw):
                err = Exception('Add usage credits or subscribe')
                err.status_code = 402
                raise err
        with patch.object(build, 'ollama', NoCredits()):
            self.assertIn('créditos', build.check_model_ready())


class MenuLoopTests(unittest.TestCase):
    def test_menu_returns_after_errors_and_exits_only_on_zero(self):
        calls = []

        def failing_pdf(args):
            calls.append('pdf')
            raise SystemExit(1)

        answers = iter(['2', '2', '0'])
        with patch.dict(build.RUNNERS, {'pdf': failing_pdf}),              patch('builtins.input', lambda *_: next(answers)),              patch('sys.argv', ['build.py']):
            self.assertEqual(build.main(), 0)
        self.assertEqual(calls, ['pdf', 'pdf'])

    def test_flag_mode_runs_once_with_exit_code(self):
        with patch.dict(build.RUNNERS, {'pdf': lambda a: (_ for _ in ()).throw(SystemExit(1))}),              patch('sys.argv', ['build.py', '--mode', 'pdf']):
            self.assertEqual(build.main(), 1)


if __name__ == '__main__':
    unittest.main()
