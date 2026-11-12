import unittest
import click
from click.testing import CliRunner

class Probe(unittest.TestCase):
    def test_matrix(self):
        for declared in [True, False]:
            for override in [True, False, None]:
                with self.subTest(declared=declared, override=override):
                    @click.command()
                    @click.option('--yes/--no', default=declared, show_default=True)
                    def cli(yes):
                        click.echo(str(yes))
                    kwargs = {} if override is None else {'default_map': {'yes': override}}
                    expected = declared if override is None else override
                    result = CliRunner().invoke(cli, ['--help'], **kwargs)
                    self.assertEqual(result.exit_code, 0)
                    self.assertIn('[default: '+('yes' if expected else 'no')+']', result.output)
                    self.assertEqual(CliRunner().invoke(cli, [], **kwargs).output.strip(), str(expected))
                    self.assertEqual(CliRunner().invoke(cli, ['--no'], **kwargs).output.strip(), 'False')
