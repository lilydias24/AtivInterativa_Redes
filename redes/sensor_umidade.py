"""Sensor de umidade do solo real via MQTT (protocolo pub/sub).

Substitui a leitura aleatória em processo (`ServidorUmidadeSolo` original) por
dois papéis de rede distintos, exatamente como o README já argumentava ser o
uso ideal do MQTT — alimentar servidores MCP com dados atualizados:

  * `SensorUmidadeIoT`   — o "dispositivo IoT": conecta-se ao broker como
    cliente MQTT e publica leituras periodicamente em `fazenda/<zona>/umidade`.
  * `ServidorUmidadeMQTT` — o servidor MCP: conecta-se ao mesmo broker,
    assina o tópico e serve a leitura mais recente através da mesma interface
    de tool (`ler_umidade`, `historico_umidade`) que o assistente já usa.

O assistente de IA não sabe (nem precisa saber) que a umidade agora chega por
uma rede real — a fronteira MCP (tools/list, tools/call) permanece idêntica.
"""

import random
import threading
import time
from collections import deque
from datetime import datetime

from fazenda_inteligente_mcp import MCPServer
from redes.mqtt_protocolo import MQTTClient


def _status_umidade(umidade: float) -> str:
    if umidade < 25:
        return "crítico (irrigar imediatamente)"
    if umidade < 40:
        return "baixo (irrigação recomendada)"
    if umidade < 65:
        return "adequado"
    return "saturado (não irrigar)"


class SensorUmidadeIoT:
    """Publica leituras simuladas (com deriva, não puro ruído) via MQTT real."""

    def __init__(self, host: str, port: int, zona: str = "zona-1", intervalo: float = 2.0):
        self.zona = zona
        self.intervalo = intervalo
        self._cliente = MQTTClient(client_id=f"sensor-{zona}", host=host, port=port)
        self._umidade_atual = round(random.uniform(30, 55), 1)
        self._rodando = False

    def iniciar(self):
        self._cliente.conectar()
        self._rodando = True
        threading.Thread(target=self._loop_publicacao, daemon=True).start()

    def _loop_publicacao(self):
        while self._rodando:
            self._umidade_atual = max(5.0, min(95.0, self._umidade_atual + random.uniform(-4, 4)))
            leitura = {
                "zona": self.zona,
                "profundidade_cm": 20,
                "umidade_pct": round(self._umidade_atual, 1),
                "status": _status_umidade(self._umidade_atual),
                "timestamp": datetime.now().isoformat(),
            }
            self._cliente.publicar(f"fazenda/{self.zona}/umidade", leitura)
            time.sleep(self.intervalo)

    def parar(self):
        self._rodando = False
        self._cliente.desconectar()


class ServidorUmidadeMQTT(MCPServer):
    """Servidor MCP de umidade do solo alimentado por um tópico MQTT real."""

    def __init__(self, host: str, port: int, zona: str = "zona-1", historico_max: int = 20):
        super().__init__("mcp-servidor-umidade-solo")
        self.zona = zona
        self._ultima_leitura: dict | None = None
        self._historico = deque(maxlen=historico_max)
        self._lock = threading.Lock()

        self.registrar_tool(
            "ler_umidade",
            "Lê a leitura mais recente recebida via MQTT do sensor de umidade do solo.",
            {"zona": "string", "profundidade_cm": "int"},
        )
        self.registrar_tool(
            "historico_umidade",
            "Retorna o histórico de leituras recebidas via MQTT nesta sessão.",
            {"zona": "string", "horas": "int"},
        )

        self._cliente = MQTTClient(client_id="mcp-servidor-umidade-solo", host=host, port=port)
        self._cliente.conectar()
        self._cliente.assinar(f"fazenda/{zona}/umidade", self._ao_receber_leitura)

    def _ao_receber_leitura(self, topico: str, dados: dict):
        with self._lock:
            self._ultima_leitura = dados
            self._historico.append(dados)

    def aguardar_primeira_leitura(self, timeout: float = 5.0):
        """Bloqueia até a primeira leitura chegar via MQTT (ou o timeout expirar)."""
        limite = time.time() + timeout
        while self._ultima_leitura is None and time.time() < limite:
            time.sleep(0.1)

    def _executar(self, nome_tool: str, argumentos: dict) -> dict:
        if nome_tool == "ler_umidade":
            with self._lock:
                if self._ultima_leitura is None:
                    return {"erro": "Nenhuma leitura recebida via MQTT ainda."}
                return dict(self._ultima_leitura)

        if nome_tool == "historico_umidade":
            with self._lock:
                historico = [
                    {"hora": leitura["timestamp"][11:19], "umidade_pct": leitura["umidade_pct"]}
                    for leitura in self._historico
                ]
            return {"zona": self.zona, "historico": historico}
