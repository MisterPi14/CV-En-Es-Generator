"""Contratos de edición de textos, independientes de Chromium y de datos privados."""
import copy
from html.parser import HTMLParser
import re
import unittest
from unittest.mock import patch

import build


def sample_cv():
    return {
        'personal_info': {
            'name': 'Example Person', 'title': 'Engineer', 'phone': '+1234567890',
            'email': 'test@example.invalid', 'location': 'City',
            'linkedin_url': 'https://example.invalid/profile',
            'github_url': 'https://example.invalid/handle',
            'portfolio_url': 'https://example.invalid/portfolio',
        },
        'summary': 'Profile text',
        'education': [{
            'degree': 'Degree', 'institution': 'School', 'period': '2020', 'gpa': '9/10',
            'Relevant subjects': 'Subject', 'Extracurricular activities': ['Club'],
            'Relevant projects': [{'title': 'Academic project', 'subitems': ['Detail']}],
        }],
        'work_experience': [{'role': 'Role', 'company': 'Company', 'description': 'Built something', 'period': '2024'}],
        'projects': [{'title': 'Project', 'description': 'Built a tool\nTested it', 'period': '2025'}],
        'skills': {'programming_languages': ['Python'], 'technologies_and_frameworks': ['Git'], 'soft_skills': ['Teamwork']},
        'courses': [{'name': 'Course', 'issuer': 'Issuer', 'year': '2023'}],
        'certifications': [{'name': 'Certificate', 'issuer': 'Issuer', 'year': '2024'}],
        'spoken_languages': [{'language': 'English', 'level': 'B2', 'certificate_url': 'https://example.invalid/cert'}],
        'academic_visits': [{'institution': 'Lab', 'focus': 'Research', 'period': '2024'}],
        'extracurriculars': [{'exp': 'Event', 'desc': 'Participated', 'date': '2025'}],
        'hackathons': [{'name': 'Competition', 'achievement': 'Built prototype', 'period': '2025'}],
    }


def render_html(data, template, lang='en'):
    with patch.object(build, 'WEASYPRINT_AVAILABLE', False), patch.object(build, '_playwright_pdf', return_value=True) as renderer:
        assert build.render_to_pdf(data, lang, template_name=template)
        return renderer.call_args.args[0]


class Structure(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, attrs))

    def handle_endtag(self, tag):
        self.tags.append(('/' + tag, []))


class EditableTextsTests(unittest.TestCase):
    def test_every_template_uses_custom_text_without_changing_structure(self):
        original = sample_cv()
        for template, cfg in build.TEMPLATES.items():
            with self.subTest(template=template):
                baseline = render_html(original, template)
                edited = copy.deepcopy(original)
                keys = set(re.findall(r'ui\.(\w+)', (build.TEMPLATES_DIR / cfg['template']).read_text(encoding='utf-8')))
                edited['ui'] = {key: f'CUSTOM_{key}' for key in keys}
                rendered = render_html(edited, template)
                for key in keys:
                    self.assertIn(f'CUSTOM_{key}', rendered)
                self.assertEqual(Structure(baseline).tags, Structure(rendered).tags)

    def test_template_precedence_empty_text_and_escaping(self):
        data = sample_cv()
        data['ui'] = {'section_work': 'General', 'label_github': '', 'document_title': '<b>CV & title</b>'}
        data['ui_templates'] = {'generation': {'section_work': 'Technical experience'}}
        before = copy.deepcopy(data)
        rendered = render_html(data, 'generation')
        self.assertIn('<h2>Technical experience</h2>', rendered)
        self.assertIn('<title>&lt;b&gt;CV &amp; title&lt;/b&gt;</title>', rendered)
        self.assertEqual(build.resolve_ui(data, 'en', 'generation')['label_github'], '')
        self.assertEqual(build.resolve_ui(data, 'en', 'capitalone')['section_work'], 'General')
        self.assertEqual(data, before)

    def test_old_yaml_defaults_remain_language_and_template_specific(self):
        data = sample_cv()
        self.assertEqual(build.resolve_ui(data, 'en', 'legacy')['label_github'], 'handle')
        self.assertEqual(build.resolve_ui(data, 'en', 'legacy')['label_linkedin'], 'Example Person')
        self.assertEqual(build.resolve_ui(data, 'en', 'generation')['label_github'], 'Github')
        self.assertEqual(build.resolve_ui(data, 'es', 'capitalone')['label_gpa'], 'Promedio')
        self.assertEqual(build.resolve_ui(data, 'en', 'capitalone')['label_gpa'], 'GPA')
        data['personal_info']['github_url'] = None
        self.assertEqual(build.resolve_ui(data, 'en', 'legacy')['label_github'], '')
        self.assertNotIn('fa-github', render_html(data, 'legacy'))

    def test_bad_settings_report_the_yaml_key(self):
        for settings, path in [
            ({'ui': None}, 'ui'),
            ({'ui': {'section_work': None}}, 'ui.section_work'),
            ({'ui': {'section_work': False}}, 'ui.section_work'),
            ({'ui': {'secton_work': 'Typo'}}, 'ui.secton_work'),
            ({'ui_templates': []}, 'ui_templates'),
            ({'ui_templates': {'unknown': {}}}, 'unknown'),
            ({'ui_templates': {'legacy': {'label_gpa': 9}}}, 'ui_templates.legacy.label_gpa'),
        ]:
            with self.subTest(settings=settings), self.assertRaisesRegex(ValueError, re.escape(path)):
                build.resolve_ui(settings, 'en', 'legacy')

    def test_translation_includes_custom_text_and_preserves_source(self):
        data = {'ui': {'section_work': 'Experiencia', 'label_portfolio': ''},
                'ui_templates': {'legacy': {'document_title': 'Mi CV'}}}
        before = copy.deepcopy(data)
        with patch.object(build, 'translate_text', side_effect=lambda text, lang, kind: f'EN:{text}'):
            translated = build.translate_cv_data(data, 'en')
        self.assertEqual(translated['ui']['section_work'], 'EN:Experiencia')
        self.assertEqual(translated['ui']['label_portfolio'], '')
        self.assertEqual(translated['ui_templates']['legacy']['document_title'], 'EN:Mi CV')
        self.assertEqual(data, before)


if __name__ == '__main__':
    unittest.main()
