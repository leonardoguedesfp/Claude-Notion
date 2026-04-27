/* global React, Icon, Shared */
const { useState, useEffect, useRef } = React;
const { Kbd } = Shared;

function LoginScreen({ onLogin, theme, onToggleTheme }) {
  const [step, setStep] = useState('returning'); // 'first-time' | 'returning'
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [user, setUser] = useState('deborah');
  const [loading, setLoading] = useState(false);
  const [tokenError, setTokenError] = useState(null);
  const [offline] = useState(false);

  const RPDATA = window.RPDATA;
  const users = RPDATA.PESSOAS.filter((p) => p.id === 'deborah' || p.id === 'leonardo');

  function submit(e) {
    e && e.preventDefault();
    setLoading(true);
    setTokenError(null);
    setTimeout(() => {
      setLoading(false);
      if (step === 'first-time' && token.length < 10) {
        setTokenError('Token inválido. Confirme se copiou a chave inteira do Notion.');
        return;
      }
      onLogin(users.find((u) => u.id === user));
    }, 700);
  }

  return React.createElement('div', { className: 'login-shell', 'data-screen-label': '01 Login' },
    React.createElement('aside', { className: 'login-art' },
      React.createElement('img', { src: 'assets/symbol-cream.png', alt: '', className: 'login-art-r' }),
      React.createElement('div', { style: { position: 'relative' } },
        React.createElement('div', { className: 'login-art-eyebrow' }, 'Ricardo Passos Advocacia'),
        React.createElement('h1', { className: 'login-art-title' }, 'Notion RPADV.'),
        React.createElement('p', { style: { fontSize: 14, lineHeight: 1.6, color: 'rgba(237,234,228,0.78)', marginTop: 18, maxWidth: 380 } },
          'Camada enxuta sobre as quatro bases do escritório: ',
          React.createElement('span', { style: { color: '#EDEAE4' } }, 'Processos, Clientes, Tarefas e Catálogo.'),
          ' Sem abrir o Notion.',
        ),
      ),
      React.createElement('div', { className: 'login-art-foot' },
        React.createElement('span', null, 'Brasília · DF · OAB/DF'),
        React.createElement('span', { style: { fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: 0, textTransform: 'none', opacity: 0.7 } }, 'v0.4.2 · build 2026.04'),
      ),
    ),

    React.createElement('div', { className: 'login-form-wrap' },
      React.createElement('form', { className: 'login-form', onSubmit: submit },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 14 } },
          React.createElement('span', { className: 'rp-eyebrow', style: { color: 'var(--app-fg-subtle)' } },
            step === 'first-time' ? 'Primeira execução' : 'Bom dia'),
          React.createElement('button', {
            type: 'button',
            className: 'btn btn-ghost',
            onClick: () => setStep(step === 'first-time' ? 'returning' : 'first-time'),
            style: { height: 24, padding: '0 8px', fontSize: 11 },
          }, step === 'first-time' ? 'Já configurei' : 'Trocar token'),
        ),
        React.createElement('h2', null,
          step === 'first-time' ? 'Configure o acesso ao Notion.' : 'Selecione o usuário ativo.'),
        React.createElement('p', { className: 'lead' },
          step === 'first-time'
            ? 'O token é guardado no Credential Manager do Windows e não sai desta máquina.'
            : 'O token está armazenado de forma segura. Escolha quem está usando o computador agora.'),

        offline && React.createElement('div', { className: 'banner banner-warning', style: { marginBottom: 12, borderRadius: 4, border: '1px solid rgba(181,138,63,0.30)' } },
          React.createElement(Icon.WifiOff, { size: 14 }),
          React.createElement('span', { className: 'banner-message' }, 'Sem conexão com a internet. Verifique sua rede.'),
        ),

        step === 'first-time' && React.createElement('div', { className: 'field' },
          React.createElement('label', null, 'Token do Notion'),
          React.createElement('div', { className: 'field-with-toggle' },
            React.createElement('input', {
              type: showToken ? 'text' : 'password',
              className: 'input',
              value: token,
              onChange: (e) => setToken(e.target.value),
              placeholder: 'secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
              autoFocus: true,
            }),
            React.createElement('button', {
              type: 'button', className: 'toggle',
              onClick: () => setShowToken((s) => !s),
            }, showToken ? 'Ocultar' : 'Mostrar'),
          ),
          tokenError
            ? React.createElement('div', { className: 'field-error' },
                React.createElement(Icon.Alert, { size: 12 }),
                tokenError)
            : React.createElement('div', { className: 'field-help' },
                'Gere em ',
                React.createElement('a', { href: '#' }, 'notion.so/my-integrations'),
                ' › ', React.createElement('em', null, 'New integration'), ' › conceda acesso às 4 bases do escritório.'),
        ),

        React.createElement('div', { className: 'field' },
          React.createElement('label', null, 'Usuário ativo'),
          React.createElement('div', { className: 'user-pick' },
            users.map((u) =>
              React.createElement('button', {
                key: u.id,
                type: 'button',
                className: `user-pick-card${user === u.id ? ' active' : ''}`,
                onClick: () => setUser(u.id),
              },
                React.createElement('span', { className: 'avatar' }, u.initials),
                React.createElement('div', null,
                  React.createElement('div', { className: 'pick-name' }, u.name),
                  React.createElement('div', { className: 'pick-role' }, u.role),
                ),
              ),
            ),
          ),
          React.createElement('div', { className: 'field-help' },
            'O usuário escolhido é registrado em todas as alterações. Você pode trocar em Configurações sem deslogar.'),
        ),

        React.createElement('button', {
          type: 'submit',
          className: 'btn btn-primary',
          style: { width: '100%', height: 38, marginTop: 6, fontSize: 13 },
          disabled: loading,
        }, loading
          ? React.createElement(React.Fragment, null,
              React.createElement('span', { className: 'spinner' }),
              step === 'first-time' ? 'Validando token…' : 'Entrando…')
          : React.createElement(React.Fragment, null,
              step === 'first-time' ? 'Validar e entrar' : 'Entrar',
              React.createElement(Kbd, null, 'Enter'))),

        React.createElement('div', { style: { marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--app-divider)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--app-fg-subtle)' } },
          React.createElement('span', { style: { letterSpacing: '0.04em' } }, 'Tema do app'),
          React.createElement('button', {
            type: 'button',
            className: 'btn btn-ghost',
            style: { height: 24, padding: '0 8px', fontSize: 11 },
            onClick: onToggleTheme,
          },
            theme === 'dark' ? React.createElement(Icon.Sun, { size: 12 }) : React.createElement(Icon.Moon, { size: 12 }),
            theme === 'dark' ? 'Claro' : 'Escuro',
          ),
        ),
      ),
    ),
  );
}

window.LoginScreen = LoginScreen;
