"""Wrapper fino sobre o keyring para armazenamento do token Notion.

No Windows usa o Windows Credential Manager; no Linux/macOS usa o backend
disponível (SecretService, Keychain, etc.).
"""
from __future__ import annotations

import keyring

from notion_bulk_edit.config import KEYRING_SERVICE, KEYRING_USERNAME


def get_token() -> str | None:
    """Recupera o token Notion do keyring do sistema.

    Retorna o token como string ou None se ainda não foi configurado.
    """
    return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)


def set_token(value: str) -> None:
    """Persiste o token Notion no keyring do sistema.

    Args:
        value: Token de integração Notion (começa com 'secret_...').
    """
    if not value or not value.strip():
        raise ValueError("Token não pode ser vazio.")
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, value.strip())


def delete_token() -> None:
    """Remove o token Notion do keyring.

    Não lança exceção se o token não existir.
    """
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass


def has_token() -> bool:
    """Retorna True se há um token armazenado no keyring."""
    return get_token() is not None
