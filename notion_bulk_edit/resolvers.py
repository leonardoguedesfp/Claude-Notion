"""Resolvers: mapeiam identificadores legíveis para page_id do Notion.

Os caches são carregados do SQLite local — não consomem a API diretamente.
"""
from __future__ import annotations

import re
import unicodedata


# ---------------------------------------------------------------------------
# Funções de normalização
# ---------------------------------------------------------------------------


def normalize_digits(text: str) -> str:
    """Remove tudo exceto dígitos do texto.

    Útil para comparar CNJ e CPF independente de formatação.

    Args:
        text: Texto com ou sem formatação numérica.

    Returns:
        String contendo apenas os dígitos do texto original.

    Exemplos:
        >>> normalize_digits("0001234-56.2023.5.10.0001")
        '00012345620235100001'
        >>> normalize_digits("123.456.789-09")
        '12345678909'
    """
    return re.sub(r"\D", "", text)


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e retira espaços extras.

    Usado para busca fuzzy em títulos do catálogo e nomes de clientes.

    Args:
        text: Texto original com possíveis acentos e maiúsculas.

    Returns:
        Texto normalizado: sem acentos, lowercase e sem espaços leading/trailing.

    Exemplo:
        >>> normalize_text("  Péticão Inicial  ")
        'peticao inicial'
    """
    if not text:
        return ""
    # Decompõe caracteres acentuados e remove as marcas de acento (categoria Mn)
    nfkd = unicodedata.normalize("NFKD", text)
    sem_acento = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


# ---------------------------------------------------------------------------
# Cache de resolução
# ---------------------------------------------------------------------------


class ResolverCache:
    """Mapeia identificadores legíveis para page_id Notion.

    Carregado do cache SQLite local — não acessa a API diretamente.
    Deve ser populado via os métodos load_* antes de usar resolve_*.

    Atributos:
        _cnj: Mapa de cnj_digits → page_id (base Processos).
        _cpf: Mapa de cpf_digits → page_id (base Clientes).
        _titulo: Mapa de titulo_normalized → page_id (base Catálogo).
    """

    def __init__(self) -> None:
        self._cnj: dict[str, str] = {}
        self._cpf: dict[str, str] = {}
        self._titulo: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def load_processos(self, rows: list[dict]) -> None:
        """Popula o índice de processos a partir de linhas do SQLite.

        Args:
            rows: Lista de dicts com chaves 'page_id' e 'cnj_digits'.
                  Exemplo: [{"page_id": "abc123", "cnj_digits": "00012345..."}]
        """
        self._cnj.clear()
        for row in rows:
            cnj = row.get("cnj_digits", "")
            pid = row.get("page_id", "")
            if cnj and pid:
                self._cnj[cnj] = pid

    def load_clientes(self, rows: list[dict]) -> None:
        """Popula o índice de clientes a partir de linhas do SQLite.

        Args:
            rows: Lista de dicts com chaves 'page_id' e 'cpf_digits'.
                  Exemplo: [{"page_id": "xyz789", "cpf_digits": "12345678909"}]
        """
        self._cpf.clear()
        for row in rows:
            cpf = row.get("cpf_digits", "")
            pid = row.get("page_id", "")
            if cpf and pid:
                self._cpf[cpf] = pid

    def load_catalogo(self, rows: list[dict]) -> None:
        """Popula o índice do catálogo a partir de linhas do SQLite.

        Args:
            rows: Lista de dicts com chaves 'page_id' e 'titulo_normalized'.
                  Exemplo: [{"page_id": "def456", "titulo_normalized": "peticao inicial"}]
        """
        self._titulo.clear()
        for row in rows:
            titulo = row.get("titulo_normalized", "")
            pid = row.get("page_id", "")
            if titulo and pid:
                self._titulo[titulo] = pid

    # ------------------------------------------------------------------
    # Resolução
    # ------------------------------------------------------------------

    def resolve_cnj(self, cnj: str) -> str | None:
        """Resolve um número CNJ para o page_id Notion correspondente.

        Normaliza o CNJ para apenas dígitos antes de buscar no índice.

        Args:
            cnj: Número CNJ com ou sem formatação
                 (ex: '0001234-56.2023.5.10.0001' ou '00012345620235100001').

        Returns:
            page_id Notion ou None se não encontrado no cache.
        """
        digits = normalize_digits(cnj)
        if not digits:
            return None
        return self._cnj.get(digits)

    def resolve_cpf(self, cpf: str) -> str | None:
        """Resolve um CPF para o page_id Notion do cliente.

        Normaliza para apenas dígitos antes de buscar.

        Args:
            cpf: CPF com ou sem formatação (ex: '123.456.789-09' ou '12345678909').

        Returns:
            page_id Notion ou None se não encontrado no cache.
        """
        digits = normalize_digits(cpf)
        if not digits:
            return None
        return self._cpf.get(digits)

    def resolve_titulo_catalogo(self, titulo: str) -> str | None:
        """Resolve um título de catálogo para o page_id Notion.

        Normaliza (sem acentos, lowercase) antes de buscar.

        Args:
            titulo: Título do item de catálogo (ex: 'Petição Inicial').

        Returns:
            page_id Notion ou None se não encontrado no cache.
        """
        norm = normalize_text(titulo)
        if not norm:
            return None
        return self._titulo.get(norm)

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ResolverCache("
            f"processos={len(self._cnj)}, "
            f"clientes={len(self._cpf)}, "
            f"catalogo={len(self._titulo)})"
        )
