"""FAZENDA INTELIGENTE — Evolução com protocolos de rede reais.

A simulação original (`fazenda_inteligente_mcp.py`) representa os servidores
MCP como objetos Python chamados em processo — ótimo para focar na arquitetura
MCP, mas sem nenhum byte de fato trafegando pela rede. Este módulo evolui o
projeto implementando de verdade dois transportes que o README já discutia
como trabalho futuro:

  1. MQTT (pub/sub) — `redes/mqtt_protocolo.py` implementa o formato de
     pacotes do MQTT 3.1.1 (subset QoS 0) sobre sockets TCP puros. Um sensor
     de umidade (`SensorUmidadeIoT`) publica leituras reais pela rede; o
     servidor MCP de umidade (`ServidorUmidadeMQTT`) assina o tópico e serve
     a leitura mais recente como tool MCP — exatamente o papel complementar
     que o README atribuía ao MQTT.

  2. HTTP + SSE — `redes/servidor_http.py` expõe o servidor MCP de clima como
     um servidor HTTP real (`http.server` da stdlib), com `tools/list` e
     `tools/call` via HTTP e um endpoint `/eventos` que empurra atualizações
     via Server-Sent Events, o segundo transporte oficial do protocolo MCP
     (voltado a servidores remotos, em contraste com stdio).

A IA e a lógica de decisão (`AssistenteAgricolaIA`) são reaproveitadas sem
nenhuma alteração: só o transporte por baixo de dois dos cinco servidores
muda, demonstrando que a arquitetura MCP é agnóstica de transporte.
"""

import time

from fazenda_inteligente_mcp import (
    AssistenteAgricolaIA,
    MCPClient,
    ServidorAlertas,
    ServidorClima,
    ServidorHistorico,
    ServidorIrrigacao,
    linha,
)
from redes.cliente_http import ServidorHTTPProxy
from redes.mqtt_protocolo import MQTTBroker
from redes.sensor_umidade import ServidorUmidadeMQTT, SensorUmidadeIoT
from redes.servidor_http import gerar_eventos_clima, iniciar_servidor_http

MQTT_HOST, MQTT_PORT = "127.0.0.1", 18830
HTTP_HOST, HTTP_PORT = "127.0.0.1", 8765


def inicializar_infraestrutura_de_rede():
    print("\nSubindo infraestrutura de rede real (sockets TCP)...\n")

    broker = MQTTBroker(MQTT_HOST, MQTT_PORT)
    broker.iniciar()
    print(f"  [MQTT]  Broker escutando em {MQTT_HOST}:{MQTT_PORT}")

    sensor = SensorUmidadeIoT(MQTT_HOST, MQTT_PORT, zona="zona-1", intervalo=2.0)
    sensor.iniciar()
    print("  [MQTT]  Sensor publicando em fazenda/zona-1/umidade a cada 2s")

    servidor_clima_local = ServidorClima()
    httpd, _ = iniciar_servidor_http(
        servidor_clima_local, HTTP_HOST, HTTP_PORT,
        eventos_geradores=gerar_eventos_clima,
    )
    print(f"  [HTTP]  Servidor de clima escutando em http://{HTTP_HOST}:{HTTP_PORT}")

    time.sleep(1.0)  # dá tempo do sensor publicar a primeira leitura via MQTT
    return broker, sensor, httpd


def inicializar_sistema_redes():
    infraestrutura = inicializar_infraestrutura_de_rede()

    client = MCPClient()
    servidor_umidade = ServidorUmidadeMQTT(MQTT_HOST, MQTT_PORT, zona="zona-1")
    servidor_umidade.aguardar_primeira_leitura()  # espera a 1ª leitura chegar via MQTT
    client.conectar(servidor_umidade)
    client.conectar(ServidorHTTPProxy("mcp-servidor-clima", f"http://{HTTP_HOST}:{HTTP_PORT}"))
    client.conectar(ServidorIrrigacao())
    client.conectar(ServidorAlertas())
    client.conectar(ServidorHistorico())

    return AssistenteAgricolaIA(client), client, infraestrutura


def rodar_demo_redes():
    linha("FAZENDA INTELIGENTE — protocolos de rede reais (MQTT + HTTP/SSE)")
    assistente, client, _ = inicializar_sistema_redes()

    linha("Ferramentas disponíveis (tools/list) — clima descoberto via HTTP real")
    for t in client.listar_todas_tools():
        print(f"  [{t['servidor']}] {t['tool']}: {t['descricao']}")

    linha("Assinando eventos SSE do servidor de clima remoto (GET /eventos)")
    proxy_clima = client.obter_servidor("mcp-servidor-clima")
    proxy_clima.assinar_eventos(
        lambda evento: print(f"  [SSE evento recebido] {evento}"), max_eventos=2
    )

    perguntas = [
        "Qual a umidade do solo agora?",
        "Preciso irrigar hoje?",
        "Como está o tempo para os próximos dias?",
        "Há algum alerta crítico agora?",
        "Mostre o histórico de decisões",
    ]
    for pergunta in perguntas:
        linha(f"Produtor: {pergunta}")
        print(f"\n Assistente IA:\n\n{assistente.responder(pergunta)}\n")
        time.sleep(0.5)

    linha("FIM DA SIMULAÇÃO COM PROTOCOLOS DE REDE REAIS")
    print(
        "\nA umidade do solo chegou via MQTT real (sockets TCP, pacotes binários"
        "\nMQTT 3.1.1 montados à mão). O clima foi servido via HTTP real"
        "\n(tools/list e tools/call por HTTP, atualizações via SSE).\n"
    )


if __name__ == "__main__":
    rodar_demo_redes()
