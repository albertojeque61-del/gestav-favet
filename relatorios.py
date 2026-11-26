"""
Geração de relatórios em PDF (fpdf2).
"""

import os
import re
from datetime import datetime
from fpdf import FPDF

from calculos import resumo_ciclo, semaforos, descrever_fim, leitura_unica
from sensibilidade import tabela_cenarios
from database import conectar


EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")


def _sanitizar(texto: str) -> str:
    """Remove caracteres fora da gama latin-1 (fpdf2 built-in fonts)."""
    if texto is None:
        return ""
    s = str(texto)
    substituicoes = {
        "—": "-",  # em dash
        "–": "-",  # en dash
        "•": "*",  # bullet
        "·": "-",  # middle dot
        "‘": "'", "’": "'",
        "“": '"', "”": '"',
        "…": "...",
        "→": "->",
    }
    for antigo, novo in substituicoes.items():
        s = s.replace(antigo, novo)
    return s.encode("latin-1", errors="replace").decode("latin-1")


def _formatar_mzn(v: float) -> str:
    return f"{v:,.2f} MZN".replace(",", " ").replace(".", ",").replace(" ", ".")


class RelatorioPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, _sanitizar("FAVET-UEM - Unidade Avícola"),
                  align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 5, _sanitizar("Sistema de Gestão Técnico-Económica"),
                  align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, _sanitizar(f"Página {self.page_no()}  |  Gerado em {datetime.now():%d/%m/%Y %H:%M}"),
                  align="C")

    # Envelopa cell e multi_cell para sanitizar automaticamente
    def cell(self, w=0, h=0, text="", **kw):
        return super().cell(w, h, _sanitizar(text), **kw)

    def multi_cell(self, w=0, h=0, text="", **kw):
        return super().multi_cell(w, h, _sanitizar(text), **kw)


def gerar_relatorio_ciclo(ciclo_id: int) -> str:
    with leitura_unica():
        return _gerar_relatorio_ciclo(ciclo_id)


def _gerar_relatorio_ciclo(ciclo_id: int) -> str:
    """Gera PDF completo do ciclo. Devolve o caminho do ficheiro."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT c.*, u.nome_completo AS utilizador
            FROM ciclos c JOIN utilizadores u ON u.id = c.utilizador_id
            WHERE c.id = %s
        """, (ciclo_id,))
        ciclo = dict(cur.fetchone())

    r = resumo_ciclo(ciclo_id)
    semas = semaforos(ciclo_id)

    pdf = RelatorioPDF()
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Relatorio do Ciclo {ciclo['codigo']}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)

    # Identificação
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "1. Identificacao do ciclo", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    campos = [
        ("Codigo", ciclo["codigo"]),
        ("Data de alojamento", ciclo["data_inicio"]),
        ("Data de encerramento", ciclo["data_fim"] or "em curso"),
        ("Linhagem", ciclo["linhagem"]),
        ("Sexo", ciclo["sexo"]),
        ("Numero de aves alojadas", f"{ciclo['n_aves_alojadas']:,}".replace(",", ".")),
        ("Fim do ciclo", descrever_fim(ciclo)),
        ("Responsavel", ciclo["utilizador"]),
        ("Estado", ciclo["estado"]),
    ]
    for k, v in campos:
        pdf.cell(60, 6, k)
        pdf.cell(0, 6, str(v), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # Indicadores técnicos
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "2. Indicadores tecnicos (zootecnicos)",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    tec = [
        ("Dia do ciclo", f"{r['dia_ciclo']}"),
        ("Aves no pavilhao", f"{r['aves_vivas']:,}".replace(",", ".")),
        ("Aves vendidas", f"{r.get('aves_vendidas', 0):,}".replace(",", ".")),
        ("Mortalidade total / %", f"{r['mortalidade_total']}  ({r['mortalidade_pct']}%)"),
        ("Viabilidade", f"{r['viabilidade_pct']}%"),
        ("Peso medio actual", f"{r['peso_actual_g']} g"),
        ("Ganho medio diario (GMD)", f"{r['gmd']} g/dia  (pinto: {r.get('peso_pinto_g', 42):.0f} g)"),
        ("Consumo acumulado de racao", f"{r['consumo_racao_kg']} kg"),
        ("Conversao alimentar (ICA)", f"{r['ica']}"),
        ("Indice de Eficiencia Produtiva (IEP)", f"{r['iep']}"),
        ("Peso vivo produzido", f"{r['peso_vivo_total_kg']} kg  (no pavilhao + vendido)"),
    ]
    if r.get("uniformidade_pct") is not None:
        tec.append(("Uniformidade (ultima pesagem)", f"{r['uniformidade_pct']}%"
                    + (f"  (CV {r['cv_pct']}%)" if r.get("cv_pct") is not None else "")))
    for k, v in tec:
        pdf.cell(80, 6, k)
        pdf.cell(0, 6, v, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # Comparação com referência
    if semas:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, f"3. Comparacao com a referencia {ciclo['linhagem']}",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(70, 6, "Indicador", border=1)
        pdf.cell(30, 6, "Actual", border=1, align="C")
        pdf.cell(30, 6, "Referencia", border=1, align="C")
        pdf.cell(30, 6, "Desvio (%)", border=1, align="C")
        pdf.cell(30, 6, "Estado", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for nome, (actual, ref, (cor, desvio)) in semas.items():
            pdf.cell(70, 6, nome, border=1)
            pdf.cell(30, 6, f"{actual:.1f}", border=1, align="C")
            pdf.cell(30, 6, f"{ref:.1f}", border=1, align="C")
            pdf.cell(30, 6, f"{desvio:+.1f}", border=1, align="C")
            label = {"verde": "OK", "amarelo": "Atencao", "vermelho": "Critico"}.get(cor, "-")
            pdf.cell(30, 6, label, border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # Indicadores económicos
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "4. Indicadores economicos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    econ = [
        ("Custos totais", _formatar_mzn(r['custo_total'])),
        ("  Custos variaveis", _formatar_mzn(r['custo_variavel'])),
        ("  Custos fixos", _formatar_mzn(r['custo_fixo'])),
        ("Custo por kg de peso vivo", _formatar_mzn(r['custo_por_kg'])),
        ("Custo por kg vendido", _formatar_mzn(r.get('custo_por_kg_vendido', 0))),
        ("Custo por ave", _formatar_mzn(r['custo_por_ave'])),
        ("Receita total", _formatar_mzn(r['receita'])),
        ("Kg vendidos", f"{r['kg_vendidos']} kg"
         + (f"  (dos quais {r['kg_carcaca']} kg em carcaca)" if r.get('kg_carcaca') else "")),
        ("Margem bruta", f"{_formatar_mzn(r['margem_bruta'])}  ({r['margem_bruta_pct']}%)"),
        ("Margem liquida", f"{_formatar_mzn(r['margem_liquida'])}  ({r['margem_liquida_pct']}%)"),
        ("Retorno sobre o investimento",
         f"{r['roi_pct']}%" if r.get("roi_pct") is not None else "sem vendas registadas"),
        ("Ponto de equilibrio (kg vendidos)", f"{r['ponto_equilibrio_kg']}"),
    ]
    for k, v in econ:
        pdf.cell(80, 6, k)
        pdf.cell(0, 6, v, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)

    # Análise de sensibilidade
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "5. Analise de sensibilidade - Margem liquida (MZN)",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Linhas = variacao do preco de venda  |  Colunas = variacao do preco da racao",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    passos_preco = [-10, -5, 0, 5, 10]
    passos_racao = [-10, 0, 10, 20]
    cenarios = tabela_cenarios(ciclo_id, passos_preco, passos_racao)

    # Grelha
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(28, 6, "Venda \\ Racao", border=1, align="C")
    for dr in passos_racao:
        pdf.cell(32, 6, f"{dr:+d}%", border=1, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    for dp in passos_preco:
        pdf.cell(28, 6, f"{dp:+d}%", border=1, align="C")
        for dr in passos_racao:
            valor = next(
                (c["margem_liquida"] for c in cenarios
                 if c["var_preco_venda"] == dp and c["var_preco_racao"] == dr),
                0.0
            )
            pdf.cell(32, 6, f"{valor:,.0f}".replace(",", "."), border=1, align="R")
        pdf.ln()

    # Vacinas e medicamentos
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT data, dia_ciclo, tipo, produto, dose, via FROM sanitario
            WHERE ciclo_id = %s ORDER BY data
        """, (ciclo_id,))
        san = cur.fetchall()
    if san:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "6. Vacinas e medicamentos aplicados", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "B", 9)
        for t, w in [("Data", 24), ("Dia", 12), ("Tipo", 30), ("Produto", 60), ("Dose", 34), ("Via", 30)]:
            pdf.cell(w, 6, t, border=1, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for s_ in san:
            d = s_["data"]
            d = f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if len(d) >= 10 else d
            for v, w in [(d, 24), (str(s_["dia_ciclo"]), 12), (s_["tipo"], 30),
                         ((s_["produto"] or "")[:38], 60), ((s_["dose"] or "")[:20], 34), ((s_["via"] or "")[:18], 30)]:
                pdf.cell(w, 6, v, border=1)
            pdf.ln()

    # Doenças e anomalias
    with conectar() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT data, dia_ciclo, tipo, sinais, suspeita, n_aves, accao FROM ocorrencias
            WHERE ciclo_id = %s ORDER BY data
        """, (ciclo_id,))
        ocs = cur.fetchall()
    if ocs:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "7. Doencas e anomalias observadas", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for o in ocs:
            d = o["data"]
            d = f"{d[8:10]}/{d[5:7]}/{d[0:4]}" if len(d) >= 10 else d
            linha = f"{d} (dia {o['dia_ciclo']}) - {o['tipo']}: {o['sinais']}"
            if o["suspeita"]:
                linha += f". Suspeita: {o['suspeita']}"
            if o["n_aves"]:
                linha += f". Aves afectadas: {o['n_aves']}"
            if o["accao"]:
                linha += f". Accao: {o['accao']}"
            pdf.multi_cell(0, 5, _sanitizar(linha), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # Observações
    if ciclo.get("observacoes"):
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 7, "8. Observacoes", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _sanitizar(ciclo["observacoes"]))

    # Guardar
    codigo_seguro = re.sub(r"[^A-Za-z0-9_-]+", "-", str(ciclo["codigo"])).strip("-") or "ciclo"
    nome_fich = f"ciclo_{codigo_seguro}_{datetime.now():%Y%m%d_%H%M}.pdf"
    caminho = os.path.join(EXPORT_DIR, nome_fich)
    pdf.output(caminho)
    return caminho
