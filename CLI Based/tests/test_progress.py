"""Barra de progreso de la traducción: conteo en seco y dibujo al pie.

Sin modelo: `translate_text` se sustituye y la terminal es un StringIO que
dice ser TTY.
"""
import io
import re
import time
import unittest
from unittest.mock import patch

import build
from test_pdf_texts import sample_cv


class FakeTTY(io.StringIO):
    encoding = 'utf-8'

    def isatty(self):
        return True


def visible(output):
    """Lo que queda en pantalla: cada \\r reescribe la línea actual."""
    lines = []
    for raw in output.split('\n'):
        lines.append(raw.split('\r')[-1].rstrip())
    return [line for line in lines if line]


class ProgressTests(unittest.TestCase):
    def test_dry_count_matches_real_calls(self):
        calls = []

        def fake(text, lang, kind):
            calls.append(kind)
            return text

        with patch.object(build, 'translate_text', side_effect=fake), \
             patch.object(build, 'ProgressBar', wraps=build.ProgressBar) as bar_cls:
            build.translate_cv_data(sample_cv(), 'es')
        total = bar_cls.call_args.args[0]
        self.assertEqual(total, len(calls))
        self.assertGreater(total, 10)

    def test_messages_print_above_and_summary_at_end(self):
        tty = FakeTTY()
        with patch('sys.stdout', tty):
            with build.ProgressBar(3, 'Traduciendo', stream=tty) as bar:
                for i in range(3):
                    bar.begin('short', f'campo {i}')
                    print(f'[LOG] mensaje {i}')
                    bar.advance()
        screen = visible(tty.getvalue())
        self.assertEqual([l for l in screen if l.startswith('[LOG]')],
                         ['[LOG] mensaje 0', '[LOG] mensaje 1', '[LOG] mensaje 2'])
        self.assertEqual(screen[-1], '[PROGRESO] 3/3 campos en 00:00')
        # Antes de cada mensaje se dibujo la barra con el campo en curso.
        self.assertIn('short: campo 0', tty.getvalue())
        self.assertRegex(tty.getvalue(), r'\[█+░*\] 1/3 +33%')

    def test_line_shows_eta_and_current_call(self):
        bar = build.ProgressBar(4, 'x', stream=FakeTTY())
        bar.started -= 60
        bar.done = 2
        bar.begin('bullets', 'Built   a\nthing')
        line = bar.line(140)
        self.assertIn('2/4  50%', line)
        self.assertIn('ETA 01:00', line)
        self.assertIn('bullets: Built a thing', line)
        self.assertLessEqual(len(bar.line(40)), 39)

    def test_disabled_without_terminal(self):
        out = io.StringIO()
        with patch('sys.stdout', out):
            with build.ProgressBar(2, 'x', stream=out) as bar:
                bar.begin('short', 'a')
                print('solo el mensaje')
                bar.advance()
        self.assertEqual(out.getvalue(), 'solo el mensaje\n')

    def test_ascii_fallback_and_stdout_restored(self):
        class AsciiTTY(FakeTTY):
            encoding = 'cp1252'
        tty = AsciiTTY()
        original = build.sys.stdout
        with build.ProgressBar(2, 'x', stream=tty) as bar:
            bar.advance()
        self.assertIs(build.sys.stdout, original)
        self.assertIn('#', tty.getvalue())
        self.assertNotIn('█', tty.getvalue())


if __name__ == '__main__':
    unittest.main()
