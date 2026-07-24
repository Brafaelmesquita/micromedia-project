# Guia — Home: conceito, polish dos KPIs, mini-legenda e nota de método

Refinamento da página **Home** (capa do dashboard). Escopo acordado:

1. Explicar de forma curta e clara **o conceito do dashboard** na própria página.
2. Deixar explícito o conceito **Hour = 25** (Overview) vs **soma das horas** (Demographics).
3. Explicar os **3 KPIs** (Population / PaS / OTS) — cards **mantidos**, só polidos.
4. Adicionar textos client-facing **em inglês**: capa + mini-legenda "How to read" + nota de método.
5. Dimensionar cards e slicers num grid harmônico; consolidar os slicers de tela via `Site Label`.

> Entrega no padrão dos outros `GUIA_*`: passo a passo para **você aplicar no Power BI Desktop**.
> Nenhum arquivo de report foi alterado por mim. Versionamento (git) na seção final.
> Measures dos 3 KPIs **já existem** (`_Measures`: `OTS`, `PaS`, `Total Population`) — nada a criar.

---

## 0. Estado atual da Home (referência)

Página `39debc1641b8a85cc90a` · canvas **1280 × 720** · fundo `#F0F0EE`.

| Elemento | Tipo | Observação |
|---|---|---|
| Faixa preta topo | shape | header, 0–117 px (único elemento preto — manter) |
| Logo olho + "Micromedia / Look to the Light" | image + textbox | manter |
| "Explore the dashboard" | pageNavigator | nav entre as 5 abas de cliente |
| "What's inside · 246 sites · 1 Mar–31 May 2026" | card (`Header Title`) | manter |
| Site · Display · Network · Month | 4 slicers | alturas e linha desalinhadas → polir |
| Population 254M · Mobile 113M · Exposure 58M | 3 cards | **manter estilo**, só alinhar/uniformizar |

Muito espaço vertical vazio entre os slicers e os cards — é onde entram a capa, a mini-legenda e a nota de método.

---

## 1. Conceito do dashboard

**Para você (o racional):** o dashboard transforma os dados da Locomizer sobre a rede DOOH da Micromedia em relatórios **pré e pós-campanha**. Toda página responde a três perguntas — **WHO** (quem é o público), **WHERE** (onde está) e **WHEN** (quando alcançar). A Home é a **capa**: enquadra o dataset (quantas telas, qual período), oferece os **filtros globais** e mostra os **3 KPIs-cabeçalho**. O nav do topo leva a Overview (WHEN), Demographics (WHO), Site Map (WHERE) e Audience Segments.

**PASTE — capa (inglês, Irish spelling).** Text box novo, logo abaixo da linha de filtros.

> **Título (H1):** Look to the Light — audience analytics for Micromedia's out-of-home network.
>
> **Subtítulo:** Who your audience is, where they are and when to reach them — across 246 digital screens in Ireland. Set the filters above, then open Overview, Demographics, Site Map or Audience Segments.

---

## 2. Os 3 KPIs — o funil 254M → 113M → 58M

**Para você.** Os três são pré-calculados pela Locomizer e compartilham o mesmo filtro (`IS_GRAND_TOTAL = 1`, `HOUR = 25`, `HasValidSite = TRUE`). Formam um funil de audiência:

| Card | Measure | Coluna | O que é |
|---|---|---|---|
| **Population** 254M | `Total Population` | `EXTRAPOLATED_USERS_2` | Toda a população que passa — audiência endereçável total. |
| **Mobile / PaS** 113M | `PaS` | `EXTRAPOLATED_NUMBER_OF_USERS` | Subconjunto que carrega celular e é de fato detectado/extrapolado — a **base medida**. |
| **Exposure / OTS** 58M | `OTS` | `EXTRAPOLATED_NUMBER_OF_EYE_CONTACTS` | Quem se move **em direção à tela**, dentro do cone de visibilidade (azimuth). |

Regra de ouro: **OTS é o número a citar como "impressões"** ao cliente — é a única métrica que considera para onde a tela aponta. Você já tem `Exposure Ratio` (OTS ÷ PaS) para mostrar a eficiência da conversão do funil.

**PASTE — labels e descritores dos cards (inglês).** Um descritor curto por card ajuda o cliente a ler o funil.

> **POPULATION** · 254M · *Everyone passing the selected screens*
> **MOBILE · PaS** · 113M · *Mobile-carrying audience actually measured*
> **EXPOSURE · OTS** · 58M · *Facing the screen — quote this as impressions*

---

## 3. Hour = 25 (Overview) vs soma das horas (Demographics)

Este é o ponto que mais confunde — e o que mais protege os números.

**Hour = 25 (headline / Overview).** A Locomizer manda uma linha especial por tela com `HOUR = 25`. **Não é uma hora real** — é o *sentinela de dia inteiro*: a contagem diária **já desduplicada**. Como uma pessoa que fica parada é contada em **cada** hora em que permanece, somar as horas 0–23 infla o total (**~1,46×**, medido no export de março). Por isso:

- KPI diário / de período → `IS_GRAND_TOTAL = 1 AND HOUR = 25` ✅ (é o que seus 3 KPIs fazem)
- Curva de "horas mais movimentadas" → `IS_GRAND_TOTAL = 1 AND HOUR < 25` (nunca inclua a 25 aqui)

**Soma das horas (Demographics).** A demografia vem como **% por hora**. Para chegar ao público por faixa/gênero você aplica o % de cada hora à população **daquela hora** e **soma as horas** (`HOUR <> 25`) — é o padrão das measures `(Hourly)` / `Age Audience (Hourly)`. É o **inverso** do Hour = 25 e reconcilia exatamente com `Total Population (Hourly)`.

> Cuidados que o pipeline já resolve (ver `demographics_notes.md`): **nunca** somar entre `RADIUS` (o % é redundante, dobraria o total) nem entre `MOVEMENT_MODALITY` (cada um é um perfil de 100% independente). O `process_demographics.py` v1.7.0 colapsa o radius na origem.

É por isso que existe a aba **QA – Inflation Stability Trend**: a razão `Hourly ÷ Daily` (measures `*(Inflation)`) prova que os dois caminhos batem, mês a mês.

**PASTE — nota de método (inglês).** Text box pequeno (11px, `#888`) no rodapé do conteúdo.

> **How the numbers are built.** Figures are extrapolated from Locomizer's mobile-location panel to the full passing population. Headline totals use the all-day figure (**Hour 25**) — the de-duplicated daily count, not the sum of hourly rows, which would double-count anyone who lingers. Demographics work the opposite way: each hour's profile is applied to that hour's audience and summed, so the age/gender split reconciles exactly to the daily total. *Population = everyone passing · Mobile (PaS) = the mobile sample measured · Exposure (OTS) = people moving toward a screen within its viewability cone.*

---

## 4. Layout e dimensionamento

Grid base: **canvas 1280 × 720**, margem externa **24 px**, gutter **16 px**, tudo encaixado numa grade de 4 px. Header preto mantido (0–117).

### 4.1 Bandas verticais (ritmo da página)

| Banda | y | altura | Conteúdo |
|---|---|---|---|
| Filtros | 132 | 64 | 4 slicers (ou 3, ver 4.4) |
| Capa (hero) | 212 | 80 | título + subtítulo |
| KPIs | 312 | 128 | 3 cards |
| Mini-legenda | 460 | 84 | "How to read" (WHO / WHERE / WHEN) |
| Nota de método | 560 | 90 | small print |
| Rodapé | 690 | 22 | fonte + slogan |

### 4.2 Slicers — polir (manter os 4)

Alinhar topo e altura de todos; **mesmo `y = 132`, mesma `height = 64`**, gutter 16.

| Slicer | x | largura |
|---|---|---|
| Site | 24 | 200 |
| Display | 240 | 430 |
| Network | 686 | 258 |
| Month (Campaign period) | 960 | 296 |

- Cabeçalho do slicer: 11px, **maiúsculas**, `#888`. Itens 12–13px.
- Fundo branco `#FFFFFF`, borda 0,5px `#DDDDDD`, canto 8px — igual aos cards (coerência).
- **Network** como slicer horizontal de botões, pílula ativa em ciano `#29B6E8`.
- **Month** → renomear rótulo para **"Campaign period"**.

### 4.3 KPIs — polir (manter os cards)

Igualar os três: **mesma largura/altura, mesmo `y`, gutter igual**, centralizados.

| Card | x | y | largura | altura |
|---|---|---|---|---|
| Population | 184 | 312 | 288 | 128 |
| Mobile / PaS | 496 | 312 | 288 | 128 |
| Exposure / OTS | 808 | 312 | 288 | 128 |

- Valor: **28–30px / peso 500 / ciano `#29B6E8`**.
- Label: 10px / 500 / `#555` / maiúsculas / letter-spacing 0.07em.
- Descritor: 11px / 400 / `#888` (itálico opcional).
- Card: branco `#FFFFFF`, borda 0,5px `#DDDDDD`, canto 8px, padding 16px, **sem sombra**.
- Ordem obrigatória da esquerda p/ direita = funil: Population → Mobile → Exposure.

### 4.4 Mini-legenda "How to read" — 3 colunas

Container em `y = 460`, `x = 24`, largura 1232, altura 84. Título de seção 16px/500 `#0A7FA8`. Três colunas iguais (~394px, gutter 24) em `x = 24 / 442 / 860`.

**PASTE (inglês):**

> **How to read this dashboard**
> **WHO** — Age, gender and social grade of the audience. → *Demographics*
> **WHERE** — Screen locations and coverage across Ireland. → *Site Map*
> **WHEN** — The busiest days and hours to be on screen. → *Overview*

### 4.5 Rodapé

**PASTE (inglês):** esquerda `Powered by Locomizer  │  Micromedia Ireland` · direita `Look to the Light`. 9–10px `#888`, borda superior 1px `#DDDDDD`.

### 4.6 Tipografia e cor (identidade)

Fonte **Inter** (ou DM Sans), **pesos 400 e 500 apenas**. Ciano `#29B6E8` é o único acento; **coral `#E05A3A` só para under-index / avisos**. Sentence case em tudo, exceto o label 10px dos KPIs.

---

## 5. Site Label — reaproveitar e consolidar slicers

Você criou `Site Label` como **coluna calculada** em `Master_Sites` — **decisão correta**:

```dax
Site Label = Master_Sites[MM ID] & " - " & Master_Sites[Display Name]
```

Coluna funciona em **linha de matriz E em slicer**; uma *measure* não funcionaria em nenhum dos dois (measure só entra na área de valores). Já está aplicada na matriz de Demographics.

**Recomendação de harmonia:** reaproveite a mesma coluna no filtro de tela da Home e **consolide `Site` + `Display` num único slicer "Screen"** — remove redundância e libera espaço:

| Slicer | x | y | largura | altura |
|---|---|---|---|---|
| Screen (`Site Label`) | 24 | 132 | 560 | 64 |
| Network | 600 | 132 | 360 | 64 |
| Campaign period (Month) | 976 | 132 | 280 | 64 |

Assim o cliente busca por **"50001 - O'Connell St"** num só campo, em vez de dois filtros paralelos.

---

## 6. Passo a passo no Power BI Desktop

1. **Filtros:** selecione os 4 slicers → Format → General → Properties → Position e aplique os X/Y/W/H da tabela 4.2 (ou 4.4 se for consolidar). Iguale `Height = 64` e o cabeçalho 11px maiúsculas.
2. **Capa:** Insert → Text box; cole o título e o subtítulo da seção 1; posicione em `x24 y212 w900`.
3. **KPIs:** selecione os 3 cards → iguale W/H (288×128) e `y=312`; distribua em 184 / 496 / 808; ajuste valor (28–30px ciano), label e adicione o descritor de cada card (seção 2).
4. **Mini-legenda:** Text box (ou 3) com o bloco da seção 4.4 em `y=460`.
5. **Nota de método:** Text box 11px `#888` com o bloco da seção 3 em `y=560`.
6. **Rodapé:** Text box com fonte + slogan em `y=690`.
7. **Replicar header:** se quiser a mesma capa nas outras abas de cliente, agrupe (right-click → Group) e Ctrl+C / Ctrl+V nas demais páginas no mesmo X/Y (mesmo método do `GUIA_header_card_radius_map.md`).
8. **Salvar** — isso atualiza os arquivos PBIP para o commit.

---

## 7. Versionamento (git)

Mesma convenção do repo (conventional commits + tag `dashboard-vX.Y.Z`; última = `dashboard-v2.8.0`). Mudança de layout + modelo, **sem pipeline e sem alterar número de KPI** → bump **minor**.

```bash
# 1. feche o .pbip no Power BI Desktop só na hora de commitar
git checkout -b feat/home-concept-layout

# 2. faça as edições no Power BI Desktop e salve

# 3. commits com escopo (evite git add -A por causa do churn de EOL;
#    o .gitattributes do repo já ajuda a conter isso)
git add pbix/MM_Dashbard__Final.SemanticModel/definition/tables/Master_Sites.tmdl
git commit -m "feat(model): Site Label calc column (MM ID - Display Name)"

git add pbix/MM_Dashbard__Final.Report/definition/pages/39debc1641b8a85cc90a
git commit -m "feat(home): concept cover, KPI polish, how-to-read + method note"

git add pbix/MM_Dashbard__Final.Report/definition/pages/c546c1a6cf3affb4eb6c
git commit -m "feat(demographics): Site Label on audience matrix"

# 4. registro de mudança + tag
git add docs/
git commit -m "docs: change record for Home concept/layout (dashboard-v2.9.0)"
git tag dashboard-v2.9.0
```

> Ajuste o prefixo `pbix/` se a raiz do seu repo for a pasta `pbix`. Registre um `docs/PR_home_concept_layout.md` seguindo o padrão dos outros PRs.

**Tag sugerida: `dashboard-v2.9.0`** (feature, layout/modelo).

---

## 8. Checklist de validação

- [ ] 4 (ou 3) slicers na mesma linha, mesmo `y` e `height`, gutters iguais.
- [ ] 3 cards iguais (288×128), mesma `y`, ordem Population → Mobile → Exposure.
- [ ] Capa, mini-legenda e nota de método em inglês, sem quebrar o funil visual.
- [ ] Valores continuam 254M / 113M / 58M (Hour 25 intacto — nada recalculado).
- [ ] `Site Label` no slicer de tela busca por "MM ID - Display Name".
- [ ] Nenhum CODE órfão (`scripts/check_join_keys.py`).
- [ ] Ciano é o único acento; coral não aparece na Home.
