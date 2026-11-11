"""Secciones: orden del YAML, `clave(Titulo)`, secciones nuevas y su traducción.

Sin navegador ni modelo: se renderiza el HTML y se intercepta la impresión.
"""
import copy
import unittest
from unittest.mock import patch

import build
from test_pdf_texts import render_html, sample_cv


def headings(html):
    """Encabezados <h2> en el orden en que aparecen."""
    out, rest = [], html
    while '<h2>' in rest:
        rest = rest.split('<h2>', 1)[1]
        text, rest = rest.split('</h2>', 1)
        out.append(text.strip())
    return out


def reorder(data, keys):
    """Mismo contenido, con las claves listadas al principio y en ese orden."""
    out = {k: data[k] for k in keys}
    out.update({k: v for k, v in data.items() if k not in out})
    return out


class SplitKeyTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(build.split_section_key('extracurriculars(Actividades)'),
                         ('extracurriculars', 'Actividades'))
        self.assertEqual(build.split_section_key('projects ( Mis proyectos ) '), ('projects', 'Mis proyectos'))
        self.assertEqual(build.split_section_key('projects()'), ('projects', None))
        self.assertEqual(build.split_section_key('Volunteer Work'), ('Volunteer Work', None))
        self.assertEqual(build.split_section_key('(Solo titulo)'), ('(Solo titulo)', None))


class OrderTests(unittest.TestCase):
    def test_sections_follow_yaml_order_in_every_template(self):
        data = reorder(sample_cv(), ['personal_info', 'projects', 'education', 'work_experience'])
        expected = {
            'legacy': ['Projects', 'Education', 'Work Experience'],
            'generation': ['Academic Project', 'Education', 'Work Experience'],
            'capitalone': ['Technical Projects', 'Education', 'Technical Experience'],
        }
        for template, first in expected.items():
            with self.subTest(template=template):
                self.assertEqual(headings(render_html(data, template))[:3], first)

    def test_shared_block_prints_at_first_key(self):
        data = reorder(sample_cv(), ['personal_info', 'courses', 'education'])
        self.assertEqual(headings(render_html(data, 'generation'))[0], 'Courses and Certifications')
        legacy = render_html(data, 'legacy')
        self.assertLess(legacy.index('bottom-metrics-grid'), legacy.index('<h2>Education</h2>'))
        data = reorder(sample_cv(), ['personal_info', 'hackathons', 'education'])
        self.assertEqual(headings(render_html(data, 'capitalone'))[0], 'Extracurriculars')

    def test_missing_key_prints_nothing(self):
        data = sample_cv()
        del data['projects']
        for template in build.TEMPLATES:
            with self.subTest(template=template):
                html = render_html(data, template)
                self.assertNotIn('Built a tool', html)


class TitleTests(unittest.TestCase):
    def test_parenthesis_renames_and_keeps_layout(self):
        base = sample_cv()
        for template in build.TEMPLATES:
            with self.subTest(template=template):
                renamed = {('projects(Mis Proyectos)' if k == 'projects' else k): v for k, v in base.items()}
                before, after = render_html(base, template), render_html(renamed, template)
                self.assertIn('<h2>Mis Proyectos</h2>', after)
                old = {'legacy': 'Projects', 'generation': 'Academic Project',
                       'capitalone': 'Technical Projects'}[template]
                self.assertEqual(before.replace(f'<h2>{old}</h2>', '<h2>Mis Proyectos</h2>'), after)

    def test_parenthesis_wins_over_ui(self):
        data = {('extracurriculars(Actividades)' if k == 'extracurriculars' else k): v
                for k, v in sample_cv().items()}
        data['ui'] = {'section_extracurriculars': 'Desde ui'}
        html = render_html(data, 'capitalone')
        self.assertIn('<h2>Actividades</h2>', html)
        self.assertNotIn('Desde ui', html)

    def test_duplicate_section_is_an_error(self):
        data = sample_cv()
        data['projects(Otra vez)'] = data['projects']
        with self.assertRaisesRegex(ValueError, 'projects'):
            render_html(data, 'capitalone')


class CustomSectionTests(unittest.TestCase):
    def custom_cv(self):
        data = sample_cv()
        data['Volunteer Work'] = [
            {'name': 'Food bank', 'period': '2025', 'url': 'https://example.invalid/x',
             'description': 'Sorted donations\nLed a team'},
            'Plain item',
        ]
        data['awards(Premios)'] = 'Won a prize'
        data['Tools'] = {'Editors': ['Vim', 'VS Code'], 'OS': 'Linux'}
        data['empty section'] = []
        return data

    def test_custom_sections_render_in_every_template(self):
        for template in build.TEMPLATES:
            with self.subTest(template=template):
                html = render_html(self.custom_cv(), template)
                titles = headings(html)
                self.assertIn('Volunteer Work', titles)
                self.assertIn('Premios', titles)
                self.assertIn('Tools', titles)
                self.assertNotIn('empty section', titles)
                for text in ('Food bank', 'Sorted donations', 'Led a team', 'Plain item',
                             'Won a prize', 'Vim | VS Code', '2025'):
                    self.assertIn(text, html)
                # Las nuevas van en su lugar del YAML: despues de las conocidas aqui.
                self.assertEqual(titles[-3:], ['Volunteer Work', 'Premios', 'Tools'])

    def test_custom_section_can_go_first_and_hide_items(self):
        data = reorder(self.custom_cv(), ['personal_info', 'Volunteer Work'])
        data['Volunteer Work'][0]['include'] = False
        pruned = build.prune_hidden(data, [])
        html = render_html(pruned, 'capitalone')
        self.assertEqual(headings(html)[0], 'Volunteer Work')
        self.assertNotIn('Food bank', html)

    def test_custom_section_hidden_whole(self):
        data = self.custom_cv()
        data['Tools']['include'] = False
        html = render_html(build.prune_hidden(data, []), 'generation')
        self.assertNotIn('<h2>Tools</h2>', html)


class TranslationTests(unittest.TestCase):
    def test_titles_and_custom_sections_are_translated_in_place(self):
        data = {
            'personal_info': {'name': 'Example Person'},
            'projects(Proyectos)': [{'title': 'Proyecto', 'description': 'Hice algo', 'period': '2025'}],
            'Voluntariado': [{'name': 'Banco', 'period': '2025', 'url': 'https://example.invalid',
                              'year': '2025', 'description': 'Ayudé\nOrganicé'}, 'Suelto'],
            'premios(Premios)': 'Gané',
        }
        before = copy.deepcopy(data)
        with patch.object(build, 'translate_text', side_effect=lambda text, lang, kind: f'EN:{text}'):
            out = build.translate_cv_data(data, 'en')
        self.assertEqual(list(out), ['personal_info', 'projects(EN:Proyectos)', 'EN:Voluntariado',
                                     'premios(EN:Premios)'])
        self.assertEqual(out['projects(EN:Proyectos)'][0]['description'], 'EN:Hice algo')
        entry = out['EN:Voluntariado'][0]
        self.assertEqual((entry['name'], entry['url'], entry['year']), ('EN:Banco', 'https://example.invalid', '2025'))
        self.assertEqual(entry['description'], 'EN:Ayudé\nOrganicé')
        self.assertEqual(out['EN:Voluntariado'][1], 'EN:Suelto')
        self.assertEqual(out['premios(EN:Premios)'], 'EN:Gané')
        self.assertEqual(out['personal_info'], {'name': 'Example Person'})
        self.assertEqual(data, before)


if __name__ == '__main__':
    unittest.main()
