# Passo a passo — rodar os scripts no MySQL Workbench

Você já criou o schema `micromedia`. Tudo o que falta agora são quatro etapas:

1. Criar a tabela `footfall_raw`
2. Habilitar o carregamento de arquivos locais (uma vez só)
3. Carregar o CSV de Março/2025
4. Rodar os scripts 01 a 05

Tempo estimado total: 5 a 10 minutos. Validei tudo num MySQL 8.0 com o CSV de Março/2025 (320.286 linhas) — os números batem exatamente com o e-mail.

---

## Etapa 1 — Criar a tabela

1. No MySQL Workbench, dê **duplo clique** no schema `micromedia` no painel esquerdo. Ele aparece em **negrito** indicando que está selecionado.
2. Vá em **File → Open SQL Script** e abra o arquivo `00_setup_create_table.sql`.
3. Clique no botão de raio (⚡) ou aperte **Ctrl+Shift+Enter** para executar todo o script.
4. O painel inferior (Output) deve mostrar "0 row(s) affected" para o DROP/CREATE e uma linha com `rows_loaded = 0` no Result Grid.

Após esta etapa, ao expandir `micromedia → Tables` no painel esquerdo, você verá `footfall_raw` listada.

---

## Etapa 2 — Habilitar `local_infile` (uma vez só)

O MySQL desabilita por padrão a leitura de arquivos locais. Você precisa ligar isso nos **dois lados**: server e client.

### 2a. No server

Abra uma query nova e execute:

```sql
SET GLOBAL local_infile = 1;
```

### 2b. No client (MySQL Workbench)

1. Vá na tela inicial (clique no ícone de **🏠 Home** no canto superior esquerdo).
2. Encontre a sua conexão `Local instance MySQL80`. Clique com o **botão direito → Edit Connection**.
3. Na janela que abre, vá na aba **Advanced**.
4. No campo **Others:** (caixa de texto na parte de baixo), adicione esta linha:

   ```
   OPT_LOCAL_INFILE=1
   ```

5. Clique em **OK**.
6. **Feche a aba da conexão atual** e abra ela de novo (duplo clique em `Local instance MySQL80` na home). Sem isso a mudança não vale.

Esta configuração é permanente — você não precisa fazer de novo no futuro.

---

## Etapa 3 — Carregar o CSV

1. Localize no seu PC o arquivo `03_Mar25_Micromedia_Footfall.csv`. Anote o caminho completo, por exemplo:

   ```
   C:\Users\seu_usuario\Downloads\03_Mar25_Micromedia_Footfall.csv
   ```

2. Abra o arquivo `00_setup_load_csv.sql` no Workbench.
3. Na linha que tem `LOAD DATA LOCAL INFILE 'C:/path/to/...'`, **troque o caminho** pelo caminho real do seu arquivo. **Use barras normais (`/`) e não barras invertidas (`\`)**, ou use barras duplas se preferir:

   ```sql
   -- Funciona:
   LOAD DATA LOCAL INFILE 'C:/Users/seu_usuario/Downloads/03_Mar25_Micromedia_Footfall.csv'
   -- Também funciona:
   LOAD DATA LOCAL INFILE 'C:\\Users\\seu_usuario\\Downloads\\03_Mar25_Micromedia_Footfall.csv'
   ```

4. Execute o script (**Ctrl+Shift+Enter**).
5. Após terminar (uns 10-30 segundos), o Result Grid deve mostrar:

   ```
   rows_loaded = 320286
   ```

   Esse é o número esperado para Março/2025.

### Se der erro "Loading local data is disabled"

Significa que o passo 2b não foi salvo. Refaça a edição da conexão e garanta que reabriu a aba dela.

### Se der erro "secure-file-priv" ou file not found

Significa que o caminho do arquivo está errado, ou tem caracteres acentuados, ou tem espaços sem aspas. Mova o arquivo para um caminho simples como `C:/dados/footfall.csv` e tente de novo.

### Plano B — se nada funcionar

Use o **Table Data Import Wizard**:

1. No painel esquerdo, **clique com o botão direito** na tabela `footfall_raw → Table Data Import Wizard**.
2. Selecione o CSV → Next.
3. Confirme que cada coluna do CSV bate com uma coluna da tabela → Next.
4. Aguarde. Para 320 mil linhas, o wizard demora **muito mais** que o LOAD DATA (15-30 minutos é normal). Mas funciona sem configuração.

---

## Etapa 4 — Rodar os scripts 01 a 05 (a demo)

Agora é só abrir cada script no Workbench e executar.

| Script | O que fazer | O que mostrar para a equipe |
|---|---|---|
| `01_hour25_vs_sum_of_hours.sql` | Abra, dê Ctrl+Shift+Enter. | O grid final mostra `sum_of_hours_0_23 = 6,042` vs `hour_25_dedup_row = 2,789` — a soma das horas dá mais que o dobro do total do dia. |
| `02_movement_modality_overlap.sql` | Idem. | A tabela da célula 50247 mostra `ALL = 8 usuários únicos` enquanto a soma dos segmentos dá `12`. A query final mostra que 37,7% das células do mês têm essa sobreposição. |
| `03_visitation_modality_overlap.sql` | Idem. | `ALL = 8` vs soma de Residents+Workers+Transient = `10`. Sobreposição em 15,8% das células do mês. |
| `04_month_wide_filter_comparison.sql` | Idem. | O grande momento: a tabela A/B/C/D mostra que sem filtro a Total Population vira **1,21 bilhão** (8× o correto), e com o filtro certo é **149,8 milhões**. |
| `05_correct_kpi_methodology.sql` | Idem. | Os números oficiais dos três KPIs (Total Population, PaS, OTS) numa única linha, mais a quebra por tela e por dia. |

### Dicas durante a apresentação

- O MySQL Workbench mostra cada SELECT em uma **aba separada** no Result Grid (Result 1, Result 2, etc) na parte de baixo. Vale clicar entre elas para mostrar tudo.
- Se quiser **executar uma query específica** em vez do script inteiro, **selecione só ela** com o mouse e aperte **Ctrl+Shift+Enter** — assim só a query selecionada roda.
- Os tempos de execução aparecem no painel **Output** lá embaixo. Útil pra mostrar que o filtro certo não é mais lento que o errado (todos rodam em menos de 1 segundo com os índices que criei no DDL).
- Se a equipe pedir para ver os dados raw de uma célula específica, basta:

  ```sql
  SELECT * FROM footfall_raw
  WHERE CODE='50247' AND DAY=9 AND HOUR=17
  ORDER BY MOVEMENT_MODALITY, VISITATION_MODALITY;
  ```

  Isso mostra as 8 combinações possíveis de modalidade para aquela célula e deixa visualmente óbvia a sobreposição.

---

## Resumo dos números que vão aparecer

| Script | Métrica chave | Valor esperado |
|---|---|---:|
| 01 | Soma de HOUR 0..23 (tela 50003, dia 3) | 6.042 |
| 01 | HOUR=25 (mesma tela/dia) | 2.789 |
| 02 | Usuários únicos vs soma de movimentos (célula 50247) | 8 vs 12 |
| 02 | % células com sobreposição de movimento no mês | 37,7% |
| 03 | Usuários únicos vs soma de visitação | 8 vs 10 |
| 03 | % células com sobreposição de visitação no mês | 15,8% |
| 04 | (A) Sem filtro | 1.210.969.108 |
| 04 | (B) ALL/ALL mas HOUR misturado | 369.039.170 |
| 04 | (C) ALL/ALL + HOUR 0..23 | 219.217.852 |
| 04 | **(D) Filtro correto** | **149.821.318** |
| 05 | Total Population (Mar/2025) | 149.821.318 |
| 05 | PaS (Mar/2025) | 66.587.252 |
| 05 | OTS (Mar/2025) | 28.102.238 |

Se os seus números baterem com a tabela acima, está tudo certo. Se algum diferir, normalmente é porque o CSV carregou linhas a mais (esqueceu de pôr `IGNORE 1 ROWS` e o header virou linha de dados, por exemplo) — confira primeiro `SELECT COUNT(*) FROM footfall_raw;` que deve dar exatamente `320286` para o arquivo de Março/2025.
