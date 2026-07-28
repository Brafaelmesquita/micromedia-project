# Review profissional — Site Map & Site Profile Card

**Versão:** v1
**Data:** 28 Jul 2026
**Autor:** Análise data / OOH
**Escopo:** Tab *Site Map* ("Who you'll reach") + card *Site Profile Card*.
**Referências:** skill `micromedia-ooh`, `references/visual_identity.md`, `references/report_templates.md`, dados em `data/processed/`.

> Objetivo: olhar de profissional de dados + planejamento OOH. O que falta, o que está errado, e o que **não** repetir do que já existe nas tabs Home / Overview / Demographics / Audience Segments.

---

## 0. Resumo executivo

Duas visões com propósitos distintos e um problema em comum: **nenhuma das duas declara métrica nem período no próprio visual, e o número-título do card está errado por ~4 ordens de grandeza.**

- **Site Map** funciona como visão de *cobertura de rede* (WHERE), mas hoje entrega um mapa sem legenda, uma lista "Top Screens" **sem métrica** e uma grade de horas **morta** (WHEN não codificado).
- **Site Profile Card** é a **única visão screen-level** do dashboard — é aí que está seu valor e é aí que ele está mais incompleto. Hoje mostra 3 coisas (um número, um donut de idade, uma barra de gênero) e nenhuma delas contextualiza *aquele* screen.

Prioridade máxima: corrigir o headline **"3bn"** (item 1). É o tipo de erro que, num pré-campanha, destrói credibilidade na frente do cliente.

---

## 1. 🔴 CRÍTICO — o headline "Total Footfall 3bn" está errado

**O que aparece:** card com "33 RPM Record Store" selecionado → **Total Footfall 3bn**.

**Verificação nos dados** (screen 33 RPM = `CODE 50426`, Urban, **Cork** — Mar/2026, regra correta `IS_GRAND_TOTAL = 1 AND HOUR = 25`):

| Métrica | Valor correto (Mar/2026) |
|---|---|
| Total Population (`EXTRAPOLATED_USERS_2`) | **≈ 481.638** |
| PaS (`EXTRAPOLATED_NUMBER_OF_USERS`) | ≈ 214.061 |
| **OTS / impressões** (`EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS`) | ≈ 84.217 |

Ou seja: o valor real de um mês para esse screen é da ordem de **centenas de milhares**, não bilhões. **"3bn" está ~4 ordens de grandeza acima** — e não bate com nenhuma soma plausível *daquele* screen (mesmo somando ingenuamente todas as 4.628 linhas do screen no mês dá 3,9M; somando os 17 meses dá ~0,1bn). O único lugar onde "bilhões" aparece é no **total da rede inteira** (≈1,85bn no período todo, correto; ≈15,7bn se somado errado).

**Diagnóstico provável (dois bugs sobrepostos):**
1. **O slicer de screen não está ligado ao KPI** — o card mostra um número de rede, não do screen selecionado. Sintoma clássico de *Edit interactions* / relacionamento faltando.
2. **A medida soma linhas em vez de filtrar** `IS_GRAND_TOTAL = 1 AND HOUR = 25` — exatamente o overcount de 8× que a skill alerta.

**Ação:** amarrar o slicer ao KPI e reescrever a medida sobre o grão dedup. Depois validar: 33 RPM / Mar-2026 deve dar **~482k** (Total Population) e **~84k** (OTS). E rotular a métrica explicitamente — "Total Footfall" é ambíguo; para cliente, impressões = **OTS**.

---

## 2. Tab *Site Map* — achados

### 2.1 "Top Screens" é uma lista sem métrica
Hoje é só `CODE – Display Name`, sem valor e sem ordenação visível. "Top" por quê? Um planejador não consegue ler a lista. **Adicionar a métrica de ranking** (OTS ou Total Population) ao lado de cada screen, **ordenado desc**, com data-bar em cyan. Incluir City + Network ajuda a ler o mix. É o mesmo conteúdo do item 4 (tabela) do template de post-campanha — reaproveitar.

### 2.2 A grade de horas (00:00–23:00) está morta
São 24 caixas cinzas sem dado. Não comunica nada. Duas saídas, ambas melhores:
- **Slicer de hora funcional** — com estado ativo/selecionado (cyan) que **filtra o mapa e o Top Screens**; ou
- **Codificar intensidade** — sombrear cada hora pelo `MM_CYAN_SCALE` (a skill já define o hour-bar intensity), virando um "quando dá pra alcançar" de fato.
Lembrete de regra: para visão horária use `IS_GRAND_TOTAL = 1 AND HOUR < 25` e **nunca** inclua `HOUR = 25`.

### 2.3 O mapa não tem legenda nem semântica de OOH
- **Sem legenda de tamanho/cor da bolha.** O que o raio significa? (deve ser ∝ `EXTRAPOLATED_USERS_2`, cor pelo cyan scale — skill). Sem legenda, o mapa é decorativo.
- **Sem diferenciação por Network** (Urban / Campus / Lifestyle / Large Format). Planejador quer ver o mix de rede no espaço. A própria skill sinaliza que faltam as cores de badge de network — resolver derivando do cyan ramp e documentar.
- **Tooltip** deve trazer: nome, city, network, footfall mensal (hoje não confirmado).
- **Só mostra Dublin.** São 249 sites, mas a rede tem Cork, Limerick, Sligo, Galway (o próprio 33 RPM é Cork). Ou o mapa não faz auto-fit nacional, ou a seleção está enviesada para Dublin. Precisa de **visão nacional + drill por cidade**.
- **Catchment não usado:** existe `docs/site_radius_circles.geojson` (círculos de raio por site) que **não está no mapa**. Catchment/isócrona é ouro em OOH ("quem vive/trabalha a X do screen") e é um diferencial real frente às outras tabs.

### 2.4 Filtros
Só Gender e Age no topo. Faltam, para uma visão de rede: **Network, City, Date range e Time of day** (o README promete todos esses). E o card lateral não reflete visualmente os filtros ativos (a skill pede filtro ativo como pill cyan).

---

## 3. Card *Site Profile Card* — o que falta

Este é o ponto mais importante da sua pergunta. O card é a **única visão de um único screen** — é o "fact sheet" de uma tela. É onde um comprador de mídia decide *aquele* ponto. Justamente por isso ele **não deve replicar** o donut de idade das tabs de rede; o valor dele é **contexto físico + comparação com a rede + timing + fit de marca**. Hoje faltam quase todos esses blocos:

1. **Ficha física do screen (ausente).** Display Name, CODE, Address, City, **Network**, `asset.setting` (indoor / street.facing / outdoor), **azimuth / direção que a tela aponta**, lat/long e um mini-mapa (ou foto). Sem isso, é impossível avaliar um único ponto. Tudo já existe no master site list.
2. **Os 3 KPIs de cabeçalho** (a skill exige): **Total Population, PaS, OTS** — não um único "footfall" ambíguo. OTS é a métrica de impressões porque considera o azimute.
3. **Busiest hours DAQUELE screen** (curva horária) — o "WHEN" no nível da tela. É diferente do agregado de rede.
4. **Heatmap hora × dia-da-semana** do screen (a skill já especifica o visual) — mostra a melhor janela de veiculação.
5. **Brand affinity top categorias do screen (ausente e essencial).** É o "por que essa tela serve à marca X". Barras horizontais de índice, linha de referência em 100, top 8. Sem isso o card não vende.
6. **Visitation mix (residents / workers / transient)** do screen — decisivo (uma record store atrai transient vs local?). Sempre como **% do total**, nunca soma absoluta (overcount 40–50%).
7. **Tendência temporal** do screen — está crescendo ou caindo mês a mês?
8. **Benchmark vs rede.** "9,8% de 18–24" não diz nada isolado. O card deveria mostrar **índice do screen vs mediana da rede** ("over-indexa 18–24 em +X%"). Aqui está o diferencial analítico real frente à tab Demographics — e a média da rede deve ser **ponderada por `EXTRAPOLATED_USERS_2`**, nunca média simples (skill).
9. **Flag de suficiência de painel.** Se o painel do screen for pequeno no período, dizer explicitamente — "reportar zero num screen ativo é pior que reportar lacuna" (skill).

---

## 4. Conformidade com a identidade visual (`visual_identity.md`)

- 🔴 **Donut de idade em arco-íris.** Usa ~7 cores distintas (azul, navy, laranja, roxo, magenta, violeta, amarelo). Viola frontalmente a regra: *"cyan é o único acento; nunca introduzir vermelho, verde, amarelo ou roxo; máximo três cores; preferir rampa monocromática cyan."* Idade deve ser **barras em cyan** (a spec diz barras para idade, donut para gênero — aqui está **invertido**), ou, se donut, rampa cyan.
- 🔴 **Coral fora de lugar.** O laranja/coral (`#E05A3A`) é reservado a **under-index e warnings**. Está sendo usado numa fatia de idade e na barra de gênero (feminino). Gênero deve ser donut: masculino `#29B6E8`, feminino `#0A7FA8`.
- **KPI:** "3bn" deveria ser cyan sobre card preto, com label 10px uppercase — e sobretudo **com a métrica e o período nomeados**.
- **Caption obrigatória ausente:** todo visual deve declarar métrica + período. Nem o card nem o mapa fazem isso.

---

## 5. O que **não** repetir (anti-redundância)

- **Idade/gênero de rede** já vivem em Overview / Demographics. No card, só faz sentido **no nível do screen e com benchmark vs rede** — senão vira um donut menor e pior da tab Demographics.
- **Social grade / ocupação / indústria** já estão na Demographics; não recriar no card — no máximo um resumo com índice.
- **Curva horária agregada** de rede provavelmente já existe; no Site Map/card ela deve ser **por screen / por seleção**, não o agregado.
- Antes de somar qualquer coisa nesses visuais, aplicar a regra de grão (`IS_GRAND_TOTAL`, `HOUR = 25`) — vale para o KPI do card e para o ranking do Top Screens.

---

## 6. Priorização sugerida

**P1 — corrige erro factual (fazer já)**
1. Bug do "3bn": ligar slicer ao KPI + reescrever medida no grão dedup; validar 33 RPM = ~482k / OTS ~84k.
2. Nomear métrica + período em card e mapa (caption).
3. Top Screens: adicionar métrica + ordenação.

**P2 — completa o valor das visões**
4. Site Profile Card: ficha física do screen + 3 KPIs (Total Pop / PaS / OTS).
5. Card: brand affinity + visitation mix do screen.
6. Card: benchmark vs mediana da rede (ponderada).
7. Mapa: legenda, network mix, tooltip padrão, visão nacional.
8. Grade de horas: virar slicer funcional **ou** heatmap de intensidade.

**P3 — diferenciais / polimento**
9. Catchment circles (`site_radius_circles.geojson`) no mapa.
10. Conformidade visual: donut idade → barras cyan; remover coral fora de warning; gênero → donut cyan.
11. Trend por screen + flag de painel insuficiente.
12. Export "one-pager do screen" (card → PDF ligado ao `report_templates.md`).

---

## 7. Versionamento

Este documento é **v1**. Próximas revisões: incrementar (`_v2`, `_v3`) e manter o histórico. Recomendo commit no git do projeto para rastreabilidade (mensagem sugerida: `docs: review v1 Site Map + Site Profile Card`).

*Audience data provided by Locomizer. Processed and presented by Micromedia.*
**Micromedia — Look to the Light**
