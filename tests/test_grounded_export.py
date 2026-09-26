"""Export literal source material without turning it into active Markdown HTML."""
import unittest
from alfred.grounded import export_markdown

class ExportTests(unittest.TestCase):
    def result(self, body, question="Opening?"):
        return {"packet":{"question":question,"evidence":[{"source_id":"S1","title":"A note", "path":"notes/A note.md","start_line":1,"end_line":3,"revision":1,"sha256":"a"*64,"excerpt":body}]},"mode":"sources","status":"sources_found"}
    def test_source_html_is_inside_literal_fence(self):
        text=export_markdown(self.result('<img src="https://example.invalid/a">'))
        self.assertIn('```text\n<img src=',text)
        self.assertIn('source note](notes/A%20note.md)',text)
    def test_source_fence_cannot_close_generated_fence(self):
        body='before\n```\n<script>example</script>'
        text=export_markdown(self.result(body))
        self.assertIn('````text\n'+body+'\n````',text)
    def test_question_and_title_do_not_create_active_markup(self):
        result=self.result('plain', '<img src=x> ![x](https://example.invalid)')
        result['packet']['evidence'][0]['title']='<script>example</script>'
        text=export_markdown(result)
        self.assertNotIn('<img',text);self.assertNotIn('<script',text)
        self.assertNotIn('![x](',text)

if __name__=='__main__':unittest.main()
