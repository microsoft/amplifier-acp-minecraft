"""Plan a connection-owned context registration without touching Instance state."""
import hashlib
import re


def registration(cfg, providers):
    identifier = cfg.get('context_provider_id')
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', identifier):
        raise ValueError('Stage an explicit connection context_provider_id first')
    port = cfg.get('control_port')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid local context port')
    if not all(isinstance(cfg.get(k), str) and cfg[k] for k in ('context_token','context_grant')):
        raise ValueError('Stage connection credentials before starting its body')
    matches = [p for p in providers if p.get('id') == identifier]
    if len(matches) > 1:
        raise ValueError('Duplicate context provider identity')
    url = f'http://127.0.0.1:{port}'
    # Existing registrations keep their secret name. A new connection cannot
    # overwrite another connection merely because both use the same player name.
    secret = cfg.get('context_secret_ref') or (matches[0].get('secret_ref') if matches else None)
    secret = secret or 'minecraft-context-'+hashlib.sha256(identifier.encode()).hexdigest()[:24]
    if not isinstance(secret,str) or not re.fullmatch('[A-Za-z0-9_-]{1,80}',secret) or secret == 'control-token':
        raise ValueError('Invalid context secret reference')
    if any(p.get('id') != identifier and p.get('secret_ref') == secret for p in providers):
        raise ValueError('Another connection owns this context secret')
    if matches and matches[0].get('url') != url:
        raise ValueError('Existing provider points elsewhere; reconcile rather than replace its route')
    label = 'Minecraft — '+cfg['username']+' — '+cfg.get('world_label','Minecraft')
    if len(label.encode()) > 200 or len(providers) >= 16 and not matches:
        raise ValueError('Context registry label or provider limit exceeded')
    provider = {'id':identifier,'label':label,
                'url':url,'secret_ref':secret}
    clean = [{k:v for k,v in p.items() if k in ('id','label','url','secret_ref')}
             for p in providers if p.get('id') != identifier]
    return {'provider':provider, 'providers':clean+[provider], 'secret_ref':secret}
