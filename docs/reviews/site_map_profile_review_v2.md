# Review profissional — Site Map & Site Profile Card

**Versão:** v2
**Data:** 28 Jul 2026
**Autor:** Análise data / OOH
**Anterior:** `site_map_profile_review_v1.md` (mantido para histórico)

> v2 incorpora as decisões tomadas com o Rafael: reclassifica achados do v1 à luz da
> intenção real das visões e detalha o redesenho estético do Site Profile Card + a
> viabilidade no Power BI.

---

## 0. O que mudou do v1 para o v2

- **"3bn" no Site Profile Card — reclassificado de 🔴 crítico para "esperado / estético".** O card mostra o valor total **sem filtro** de propósito (alimenta o card do Site Map, que funciona). Não é bug. O número em si não é o foco desta visão.
- **Site Map — intenção confirmada:** mostrar a **distribuição geográfica da rede**. Os slicers **Network, Site e Month** (os mesmos do Overview) filtram o mapa. O ajuste do mapa já foi implementado pelo Rafael.
- **Filtro de hora no mapa:** decidido **não** por padrão — hora transforma a visão de distribuição em daypart (outra pergunta) e obriga a trocar o grão (`HOUR<25`, nunca somar). Fica como modo separado, se um dia for necessário.
- **Top Screens por gênero/idade — regra correta registrada** (seção 2).
- **Foco atual:** redesenho estético do Site Profile Card (seção 3).

---

## 1. Site Map — estado e definições

Propósito: distribuição geográfica da rede (WHERE). Métrica das bolhas = total mensal dedup (`IS_GRAND_TOTAL=1 AND HOUR=25`). Slicers Network / Site / Month espelham o Overview e filtram o mapa. Sem filtro de hora por padrão.

---

## 2. Top Screens filtrado por gênero + idade — regra de cálculo

Idade e gênero vivem na tabela **Demographics** (não no Footfall). Verificado nos dados: `REACH_PCT` é composição que **fecha 100% por (screen, hora, modalidade)** e só existe **hora 0–23 — não há linha all-day (HOUR=25)** na demografia.

Consequências para rankear screens por um segmento:

1. **Não rankear pelo `%`.** Uma tela minúscula pode ser 90% de um segmento e ter quase nenhuma audiência. Rankear por **população absoluta do segmento = volume × %**.
2. **A % só existe por hora.** O número mensal/all-day correto pondera cada hora pelo footfall daquela hora:
   `Pop_segmento(screen) = Σ_hora [ Footfall(screen,hora) × %(screen,hora,segmento) ]`
   (ponderar por `EXTRAPOLATED_USERS_2` da hora — nunca média simples; fixar `MOVEMENT_MODALITY='All'`).
   Alternativa equivalente, se o modelo já guarda o % mensal ponderado por footfall:
   `Pop_segmento ≈ TotalPop_dedup(HOUR=25) × %mensal_ponderado(segmento)`.
3. **O contador de população por hora é o motor da medida — mas NÃO exige um slicer de hora visível.** Para o ranking do mês inteiro, o usuário só escolhe gênero+idade; a hora fica interna à medida.
4. **Slicer de hora só vira necessário** se o requisito for dayparting ("top screens de feminino 18-24 entre 07:00–09:00"). Aí a medida soma só as horas selecionadas.

---

## 3. Site Profile Card — redesenho estético (identidade da marca)

Referência: `references/visual_identity.md`. Diagnóstico do card atual: donut de idade em ~7 cores (arco-íris) e barra de gênero em coral — ambos fora da paleta (cyan é o único acento; coral só para under-index/warning; máx. 3 cores).

Decisões acordadas:

1. **Donut de idade → rampa monocromática cyan** (claro→escuro por faixa etária). Encoding natural de idade. Paleta usada no mockup: Under 18 `#A8E4F5`, 18-24 `#7FD3EF`, 25-34 `#52C1E9`, 35-44 `#29B6E8`, 45-54 `#1D97C6`, 55-64 `#0A7FA8`, 65+ `#00566E`.
2. **Legenda lateral com o valor junto** (ex.: "Under 18 · 21.5%") e **remover as leader lines** com % (poluição). Um sistema de rótulo só.
   *Alternativa mais legível:* 7 faixas em **barras horizontais cyan** (o guia especifica idade = barras) leem melhor que 7 tons do mesmo azul; nesse caso o donut fica só para gênero.
3. **Gênero → maior contraste dentro da marca.** Dois cyans quase iguais não separam. Usar as **duas pontas da rampa**: masculino `#29B6E8` (cyan), feminino `#003D52` (navy). Coral fica proibido aqui.
4. **KPI em chip:** fundo preto, label 10px maiúscula cinza (`#888888`), valor grande em cyan (`#29B6E8`). Padrão "cyan on black" do guia.
5. **Header com contexto da tela:** `Custom ID` + `Display Name` + badge de **Network** (Urban/Campus/Lifestyle/Large Format) + cidade. Substitui a caixa grande de dropdown (mais leve → **ganha** espaço, não perde). Metadados vêm do master site list.
6. **Container:** card branco, borda 0.5px `#DDDDDD`, cantos 12px, sem sombra.

---

## 4. Viabilidade no Power BI

Reproduzível **~100% nativo, sem custom visual**:

| Elemento | Como | Fidelidade |
|---|---|---|
| Donut rampa cyan | Data colors por categoria (hex custom) | Exato |
| KPI chip preto/cyan | Visual Card: fundo preto, cor do valor, label uppercase | Exato |
| Gênero barra 100% | Stacked bar 100% (1 categoria) + data labels + data colors | Exato |
| Header ID + Display Name | Card / multi-row card | Exato |
| Badge Network "URBAN" | Card fundo cyan-claro + rounded corners | ~90% (não é pílula real) |
| Container branco 12px | Background + border + rounded corners | Exato |
| Legenda com valor junto | Matrix/table ao lado estilizado, ou detail labels | Funcional, não é a legenda nativa |
| Fonte Inter | Selecionar fonte; instalar se faltar (padrão PBI = Segoe) | Depende da fonte instalada |

Ressalvas: (a) legenda-com-valor exige um matrix lateral ou detail labels; (b) o badge em pílula é aproximado; (c) controle fino de leader lines é limitado — resolver desligando labels e usando legenda lateral + tooltip; (d) Inter pode cair em fallback.

---

## 5. Versionamento

v2 mantém o v1 no histórico. Commit sugerido: `docs(review): site map + profile card review v2 (card redesign + PBI feasibility)`.

*Audience data provided by Locomizer. Processed and presented by Micromedia.*
**Micromedia — Look to the Light**
