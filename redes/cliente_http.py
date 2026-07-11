"""Cliente MCP client-side que fala HTTP de verdade com um servidor remoto.

`ServidorHTTPProxy` tem a mesma interface (`listar_tools`, `chamar_tool`) que
um `MCPServer` local, mas cada chamada de fato sai pela rede via HTTP — o
`MCPClient` original nem percebe a diferença, o que demonstra na prática a
transparência de transporte que o protocolo MCP promete: a IA e a lógica de
negócio não mudam, só a implementação por baixo do tópico "mcp-servidor-clima".
"""

import http.client
import json
import threading
import urllib.request
from urllib.parse import urlparse


class ServidorHTTPProxy:
    def __init__(self, nome: str, base_url: str):
        self.nome = nome
        self.base_url = base_url.rstrip("/")
        # Descoberta dinâmica real: tools/list é buscado por HTTP, não hardcoded.
        self._tools_remotas = self._descobrir_tools()

    def _descobrir_tools(self) -> list[dict]:
        with urllib.request.urlopen(f"{self.base_url}/tools/list") as resp:
            return json.loads(resp.read().decode("utf-8"))

    def listar_tools(self) -> list[dict]:
        return self._tools_remotas

    def chamar_tool(self, nome_tool: str, argumentos: dict) -> dict:
        corpo = json.dumps({"tool": nome_tool, "args": argumentos}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/tools/call",
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def assinar_eventos(self, on_evento, max_eventos: int = 3):
        """Consome o stream SSE (`/eventos`) em uma thread de fundo."""

        def _consumir():
            partes = urlparse(self.base_url)
            conn = http.client.HTTPConnection(partes.hostname, partes.port)
            try:
                conn.request("GET", "/eventos")
                resp = conn.getresponse()
                recebidos = 0
                while recebidos < max_eventos:
                    linha = resp.fp.readline().decode("utf-8")
                    if not linha:
                        break
                    if linha.startswith("data:"):
                        evento = json.loads(linha[len("data:"):].strip())
                        on_evento(evento)
                        recebidos += 1
            except (ConnectionError, OSError):
                pass
            finally:
                conn.close()

        threading.Thread(target=_consumir, daemon=True).start()
