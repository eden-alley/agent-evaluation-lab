import click
@click.command(context_settings={'default_map':{'long':True}})
@click.option('--long/--short','-l/-s',is_flag=True,show_default=True,help='Detailed listing')
def main(long):click.echo('long' if long else 'short')
if __name__=='__main__':main()
