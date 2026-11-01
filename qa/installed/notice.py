"""Seed fake paused keys only inside the disposable installed Search package."""
from pathlib import Path
from wam import cli
SHA = '679be8ce8eea6ba13bf031104ea991202b5c373a'
assert (Path.home() / 'native-web-qa/disposable.json').read_text().strip() == SHA
c = cli.Config()
assert (c.runtipi_root / 'apps/wizardapps/wizard-search/.wizard-commit').read_text().strip() == SHA
cli.write_user_env(c.runtipi_root, 'wizard-search', {
    'WIZARD_SEARCH_PROVIDER_POLICY': 'free-only', 'WIZARD_SEARCH_APPROVED_UPGRADES': '',
    'FIRECRAWL_CLOUD_API_KEY': 'qa-not-a-real-key', 'FIRECRAWL_CLOUD_URL': 'http://127.0.0.1:9',
    'BRIGHTDATA_API_TOKEN': 'qa-not-a-real-key', 'FIRECRAWL_ROUTER_URL': 'http://127.0.0.1:9',
    'TINFOIL_API_KEY': '', 'TINFOIL_PROXY_URL': '', 'WIZARD_SEARCH_SOCKS': '',
})
cli.app_lifecycle(c, 'restart', 'wizard-search')
print('NOTICE_FIXTURE=paused fake keys; no search/overview request in this phase')
