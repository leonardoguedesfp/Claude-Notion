"""Cliente Notion API v1 para o escritório RPADV.

Cobre autenticação, paginação automática, rate limiting e retries em 429.
"""
from __future__ import annotations

import time
from typing import Callable

import requests

from notion_bulk_edit.config import NOTION_API_BASE, NOTION_VERSION, RATE_LIMIT_RPS

# ---------------------------------------------------------------------------
# Exceções personalizadas
# ---------------------------------------------------------------------------


class NotionAuthError(Exception):
    """Levantada quando a API retorna HTTP 401 (token inválido ou expirado)."""


class NotionAPIError(Exception):
    """Levantada para erros HTTP genéricos da API Notion."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"HTTP {status_code}: {message}")


class NotionRateLimitError(NotionAPIError):
    """Levantada quando os retries em 429 se esgotam."""


# ---------------------------------------------------------------------------
# Cliente principal
# ---------------------------------------------------------------------------


class NotionClient:
    """Cliente HTTP para a API Notion v1.

    Aplica rate limiting (RATE_LIMIT_RPS), retries automáticos em 429 e
    conversão de erros HTTP em exceções tipadas.

    Args:
        token: Token de integração Notion (secret_...).
    """

    _MAX_RETRIES: int = 3
    _DEFAULT_RETRY_AFTER: float = 3.0

    def __init__(self, token: str) -> None:
        self._token = token
        self._min_interval: float = 1.0 / RATE_LIMIT_RPS
        self._last_call: float = 0.0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            }
        )
        # Cache: database_id → data_source_id (Notion API 2025-09-03)
        self._ds_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _throttle(self) -> None:
        """Aguarda o intervalo mínimo entre chamadas para respeitar o rate limit."""
        now = time.monotonic()
        elapsed = now - self._last_call
        wait = self._min_interval - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        """Executa uma requisição HTTP com rate limiting e retries.

        Args:
            method: Método HTTP ('GET', 'POST', 'PATCH', etc.).
            path: Caminho relativo à base da API (ex: '/users/me').
            json: Body JSON da requisição.
            params: Query params.

        Returns:
            Resposta JSON deserializada.

        Raises:
            NotionAuthError: Token inválido (HTTP 401).
            NotionRateLimitError: Rate limit persistente após retries.
            NotionAPIError: Qualquer outro erro HTTP da API.
        """
        url = f"{NOTION_API_BASE}{path}"
        retries = 0

        while True:
            self._throttle()
            resp = self._session.request(method, url, json=json, params=params)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 401:
                raise NotionAuthError(
                    "Token inválido ou sem permissão. "
                    "Configure um novo token via 'Configurações > Token'."
                )

            if resp.status_code == 429:
                if retries >= self._MAX_RETRIES:
                    raise NotionRateLimitError(
                        429,
                        f"Rate limit atingido após {self._MAX_RETRIES} tentativas.",
                    )
                retry_after = float(
                    resp.headers.get("Retry-After", self._DEFAULT_RETRY_AFTER)
                )
                time.sleep(retry_after)
                retries += 1
                continue

            # Erro genérico — tenta extrair mensagem do body
            try:
                body = resp.json()
                msg = body.get("message", resp.text)
            except Exception:
                msg = resp.text or resp.reason or "Erro desconhecido"

            raise NotionAPIError(resp.status_code, msg)

    # ------------------------------------------------------------------
    # Endpoints públicos
    # ------------------------------------------------------------------

    def _resolve_ds_id(self, database_id: str) -> str:
        """Resolve database_id → data_source_id (cached).

        Notion API 2025-09-03 replaced /databases/{id}/query with
        /data_sources/{id}/query, where the data_source_id is obtained
        from the database object's 'data_sources' array.
        The result is cached so each database is looked up only once.
        """
        if database_id in self._ds_cache:
            return self._ds_cache[database_id]
        db = self._request("GET", f"/databases/{database_id}")
        sources: list[dict] = db.get("data_sources") or []
        if not sources:
            raise NotionAPIError(
                404,
                f"Nenhum data source encontrado para o banco {database_id}. "
                "Verifique se a integração tem acesso a essa base no Notion "
                "(⋯ → Conexões → adicionar integração).",
            )
        ds_id: str = sources[0]["id"]
        self._ds_cache[database_id] = ds_id
        return ds_id

    def me(self) -> dict:
        """Valida o token retornando os dados do bot/usuário autenticado.

        Returns:
            Objeto User da API Notion.

        Raises:
            NotionAuthError: Token inválido.
        """
        return self._request("GET", "/users/me")

    def query_database(
        self,
        database_id: str,
        filter: dict | None = None,
        sorts: list | None = None,
        start_cursor: str | None = None,
        page_size: int = 100,
    ) -> dict:
        """Executa uma única página de resultados de uma base Notion.

        Args:
            database_id: ID da base (com ou sem hífens UUID).
            filter: Filtro Notion (estrutura da API).
            sorts: Lista de critérios de ordenação.
            start_cursor: Cursor de paginação.
            page_size: Número de resultados por página (máx. 100).

        Returns:
            Objeto de resposta da API com 'results', 'has_more' e 'next_cursor'.
        """
        body: dict = {"page_size": min(page_size, 100)}
        if filter:
            body["filter"] = filter
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor

        ds_id = self._resolve_ds_id(database_id)
        return self._request("POST", f"/data_sources/{ds_id}/query", json=body)

    def query_all(
        self,
        database_id: str,
        filter: dict | None = None,
        sorts: list | None = None,
        on_progress: Callable[[int], None] | None = None,
    ) -> list[dict]:
        """Pagina automaticamente todos os resultados de uma base.

        Args:
            database_id: ID da base Notion.
            filter: Filtro opcional.
            sorts: Ordenação opcional.
            on_progress: Callback chamado com o total acumulado após cada página.

        Returns:
            Lista com todos os objetos Page retornados pela base.
        """
        results: list[dict] = []
        cursor: str | None = None

        while True:
            page = self.query_database(
                database_id,
                filter=filter,
                sorts=sorts,
                start_cursor=cursor,
            )
            results.extend(page.get("results", []))

            if on_progress:
                on_progress(len(results))

            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")

        return results

    def get_page(self, page_id: str) -> dict:
        """Retorna os metadados e propriedades de uma página Notion.

        Args:
            page_id: ID da página.

        Returns:
            Objeto Page da API Notion.
        """
        return self._request("GET", f"/pages/{page_id}")

    def update_page(self, page_id: str, properties: dict) -> dict:
        """Atualiza propriedades de uma página existente.

        Args:
            page_id: ID da página a atualizar.
            properties: Dicionário de propriedades no formato da API Notion.
                Ex: {"Status": {"select": {"name": "Ativo"}}}

        Returns:
            Objeto Page atualizado.
        """
        return self._request(
            "PATCH",
            f"/pages/{page_id}",
            json={"properties": properties},
        )

    def create_page(self, database_id: str, properties: dict) -> dict:
        """Cria uma nova página em uma base Notion.

        Args:
            database_id: ID da base onde a página será criada.
            properties: Propriedades iniciais no formato da API Notion.

        Returns:
            Objeto Page recém-criado.
        """
        return self._request(
            "POST",
            "/pages",
            json={
                "parent": {"database_id": database_id},
                "properties": properties,
            },
        )

    def archive_page(self, page_id: str) -> dict:
        """Arquiva (exclui logicamente) uma página Notion.

        Args:
            page_id: ID da página a arquivar.

        Returns:
            Objeto Page arquivado.
        """
        return self._request(
            "PATCH",
            f"/pages/{page_id}",
            json={"archived": True},
        )

    def list_users(self) -> list[dict]:
        """Lista todos os usuários do workspace.

        Pagina automaticamente até obter todos os membros.

        Returns:
            Lista de objetos User da API Notion.
        """
        users: list[dict] = []
        cursor: str | None = None

        while True:
            params: dict = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            resp = self._request("GET", "/users", params=params)
            users.extend(resp.get("results", []))

            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        return users
