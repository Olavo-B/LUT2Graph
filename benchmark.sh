#!/bin/bash

# ==============================================================================
# LUT2Graph - Suite de Benchmarks Automatizada (PaviaU)
# ==============================================================================
# Este script executa todas as estratégias de poda (estrutural e data-driven)
# para o dataset PaviaU, salvando os resultados, grafos .gexf e relatórios em
# pastas organizadas dentro do diretório 'results/'.
# ==============================================================================

# Variáveis de Caminho (Facilita a manutenção do script)
NETLIST="./misc/data/paviaU/result.json"
TEST_DATA="./misc/data/paviaU/TreeLUT/testbench/X_test.mem"
TEST_LABELS="./misc/data/paviaU/TreeLUT/testbench/y_test.mem"
MAIN_SCRIPT="src/benchmark_complex_net.py"

echo "Iniciando a bateria de testes LUT2Graph para o dataset PaviaU..."
echo "=============================================================================="

# ------------------------------------------------------------------------------
# 1. Poda de Redundância Estrita (Baseline Hardware-Aware)
# ------------------------------------------------------------------------------
echo "[1/6] Executando: Baseline (Zero-Tolerance)"
echo "      -> Corta apenas arestas e nós no limiar matemático exato (1/16)."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_Baseline_Strict" \
  --prune \
  --sens-threshold 0.07 \
  --bias-lower 0.07 \
  --bias-upper 0.93 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "------------------------------------------------------------------------------"

# ------------------------------------------------------------------------------
# 2. Poda por Centralidade (PageRank)
# ------------------------------------------------------------------------------
echo "[2/6] Executando: Centralidade (PageRank - 5% de corte)"
echo "      -> Cega para a lógica. Remove nós perifericamente menos conectados."
echo "      -> Esperado: Queda drástica na acurácia devido ao efeito cascata."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_Centralidade_PageRank" \
  --prune \
  --method centrality \
  --centrality-metric pagerank \
  --drop-fraction 0.05 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "------------------------------------------------------------------------------"

# ------------------------------------------------------------------------------
# 3. Poda Topológica K-Core
# ------------------------------------------------------------------------------
echo "[3/6] Executando: Decomposição K-Core (Shell 3)"
echo "      -> Descasca a rede removendo as camadas estruturais mais externas."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_KCore_Shell3" \
  --prune \
  --method kcore \
  --max-shell 3 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "------------------------------------------------------------------------------"

# ------------------------------------------------------------------------------
# 4. Extração Dinâmica de Backbone
# ------------------------------------------------------------------------------
echo "[4/6] Executando: Extração de Backbone (Sensibilidade < 0.10)"
echo "      -> Remove arestas fracas, mas protege as pontes ativamente"
echo "         para não fragmentar o componente gigante (WCC)."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_Backbone_Sens010" \
  --prune \
  --method backbone \
  --sens-threshold 0.10 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "------------------------------------------------------------------------------"

# ------------------------------------------------------------------------------
# 5. Poda de Profundidade Parabólica (Depth-Aware)
# ------------------------------------------------------------------------------
echo "[5/6] Executando: Profundidade Parabólica (5% de corte)"
echo "      -> Protege a raiz e as folhas. Foca apenas no ventre redundante."
echo "      -> Esperado: Sobrevivência de acurácia muito superior à Centralidade."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_Parabolica_5PorCento" \
  --prune \
  --method depth \
  --drop-fraction 0.05 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "------------------------------------------------------------------------------"

# ------------------------------------------------------------------------------
# 6. Poda por Entropia de Shannon (Data-Driven)
# ------------------------------------------------------------------------------
echo "[6/6] Executando: Entropia de Shannon (5% de corte)"
echo "      -> Alveja nós de baixa entropia (previsíveis)."
echo "      -> Esperado: Prova de que nós de baixa entropia são, na verdade,"
echo "         detectores vitais de edge-cases (a acurácia deve cair)."
python $MAIN_SCRIPT $NETLIST \
  --test-name "PaviaU_Entropia_5PorCento" \
  --prune \
  --method entropy \
  --drop-fraction 0.05 \
  --test-data $TEST_DATA \
  --test-labels $TEST_LABELS
echo "=============================================================================="
echo "Bateria de testes concluída com sucesso! Verifique a pasta 'results/'."