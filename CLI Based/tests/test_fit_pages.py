"""Ajuste a una página con Chromium real: poco, mediano, mucho y muchísimo contenido.

Para cada template de una página exige que el PDF tenga exactamente 1 página y
que la última sección termine en el margen inferior (página llena al 100 %).
Usa datos inventados; necesita Playwright con Chromium (se omite si falta).
"""
import copy
import tempfile
import unittest
from pathlib import Path

import build
from test_pdf_texts import sample_cv

FIT_TEMPLATES = [name for name, cfg in build.TEMPLATES.items() if cfg.get('fit_one_page')]


def tiny():
    data = sample_cv()
    keep = ('personal_info', 'summary', 'projects')
    return {k: v for k, v in data.items() if k in keep}


def scaled(projects, bullets):
    data = sample_cv()
    data['projects'] = [{
        'title': f'Project {i}', 'period': '2025',
        'description': '\n'.join(f'Built component {j} of project {i} with a reasonably long '
                                 f'sentence that wraps across the line' for j in range(bullets)),
    } for i in range(projects)]
    data['Volunteer Work'] = [{'name': f'Activity {i}', 'period': '2024',
                               'description': 'Helped organize an event'} for i in range(3)]
    return data


CASES = {
    'tiny': tiny,
    'medium': sample_cv,
    'large': lambda: scaled(8, 4),
    'huge': lambda: scaled(30, 6),
}


@unittest.skipUnless(build.PLAYWRIGHT_AVAILABLE, 'Playwright no está instalado')
class FitPageTests(unittest.TestCase):
    def test_every_size_fills_exactly_one_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            for template in FIT_TEMPLATES:
                for case, make in CASES.items():
                    with self.subTest(template=template, case=case):
                        out = Path(tmp) / f'{template}-{case}.pdf'
                        self.assertTrue(build.render_to_pdf(copy.deepcopy(make()), 'en',
                                                            str(out), template))
                        self.assertEqual(build._count_pdf_pages(out), 1)
                        fit = dict(build.LAST_FIT)
                        # La última sección termina en el margen inferior (±1 px).
                        self.assertAlmostEqual(fit['bottom'], fit['target'], delta=1.0, msg=fit)
                        # El sobrante repartido es menos de una línea: la letra
                        # ya es la mayor posible.
                        self.assertGreater(fit['content'] / fit['target'], 0.95, msg=fit)
                        print(f"  {template:<11} {case:<7} letra {fit['size']:>6}px  "
                              f"contenido {fit['content'] / fit['target']:.1%}  final 100%")


if __name__ == '__main__':
    unittest.main()
