"""Descriptive macro radar and rolling one-month baseline evaluation."""
import argparse
import csv
import hashlib
from html import escape
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
SECTORS = ['Secteur public hors AC', 'Secteur privé', 'Autres sociétés financières']
METHODS = ('last_month', 'same_month_last_year', 'drift_12m')
LABELS = {'last_month': 'Dernier mois', 'same_month_last_year': 'Même mois, année précédente',
          'drift_12m': 'Dérive sur 12 mois'}
LIMITATION = ('Évaluation rétrospective sur les séries révisées disponibles. Les dates de publication '
              'historiques sont inconnues : ce résultat ne mesure pas une performance en temps réel.')


def month_number(period):
    return int(period[:4]) * 12 + int(period[5:7]) - 1


def forecast(history, method):
    if len(history) < 13:
        raise ValueError('13 observations au moins sont nécessaires')
    if method == 'last_month':
        return history[-1]
    if method == 'same_month_last_year':
        return history[-12]
    if method == 'drift_12m':
        return history[-1] + (history[-1] - history[-13]) / 12
    raise ValueError('Méthode inconnue')


def evaluate(series, horizon=24):
    series = sorted(series, key=lambda r: r['period_start'])
    if horizon < 1 or len(series) < horizon + 24:
        raise ValueError('Historique insuffisant : au moins 24 mois avant le test')
    periods = [month_number(r['period_start']) for r in series]
    if any(b-a != 1 for a, b in zip(periods, periods[1:])):
        raise ValueError('La série doit être mensuelle, continue et sans doublon')
    values = [r['value'] for r in series]
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError('Encours invalide')
    split = len(values) - horizon
    # Common fixed scale, computed only on pre-test training observations.
    scale = statistics.mean(abs(values[i]-values[i-1]) for i in range(1, split))
    predictions, metrics = [], []
    for method in METHODS:
        errors = []
        for i in range(split, len(values)):
            predicted = forecast(values[:i], method)
            error = values[i] - predicted
            errors.append(error)
            predictions.append({'method': method, 'target_period': series[i]['period_start'],
                                'training_end': series[i-1]['period_start'],
                                'actual_mdh': values[i], 'prediction_mdh': predicted,
                                'error_mdh': error})
        mae = statistics.mean(abs(e) for e in errors)
        metrics.append({'method': method, 'n': horizon, 'mae_mdh': mae,
                        'rmse_mdh': math.sqrt(statistics.mean(e*e for e in errors)),
                        'mase': mae / scale if scale else None})
    return {'test_start': series[split]['period_start'], 'test_end': series[-1]['period_start'],
            'training_end_initial': series[split-1]['period_start'], 'horizon_months': 1,
            'evaluation_points': horizon, 'scale_mae_training_mdh': scale,
            'metrics': metrics, 'predictions': predictions, 'limitation': LIMITATION}


def summarize(rows):
    if len({r['observation_key'] for r in rows}) != len(rows):
        raise ValueError('Clés métier dupliquées dans Gold')
    bam = [r for r in rows if r['source_id']=='bam_credit' and r['frequency']=='monthly'
           and r['unit']=='million_MAD' and r['geography']=='National']
    total = sorted([r for r in bam if r['category_code']=='Crédit bancaire'], key=lambda r:r['period_start'])
    if not total:
        raise ValueError('Série crédit total absente')
    latest = total[-1]
    sectors = []
    for name in SECTORS:
        matching = [r for r in bam if r['category_code']==name and r['period_start']==latest['period_start']]
        if len(matching) != 1:
            raise ValueError(f'Secteur absent ou ambigu : {name}')
        sectors.append({**matching[0], 'share_pct': 100*matching[0]['value']/latest['value'] if latest['value'] else None})
    if abs(sum(r['value'] for r in sectors)-latest['value']) > 0.01:
        raise ValueError('Les trois secteurs ne réconcilient pas le total à 0,01 MDH près')
    hcp = [r for r in rows if r['source_id']=='hcp_ipc' and r['frequency']=='annual'
           and r['geography']=='National' and r['unit']=='index_2017_100']
    general = sorted([r for r in hcp if r['category_code']=='GR'], key=lambda r:r['period_start'])
    if not general:
        raise ValueError('IPC général national absent')
    year = general[-1]['period_start']
    divisions = sorted([r for r in hcp if r['period_start']==year and len(r['category_code'])==2
                        and r['category_code'].isdigit()], key=lambda r:r['category_code'])
    if len(divisions) != 12:
        raise ValueError('Les 12 divisions IPC sont requises')
    return {'credit_total': total, 'credit_latest': latest, 'credit_sectors': sectors,
            'cpi_general': general, 'cpi_latest': general[-1], 'cpi_divisions': divisions,
            'evaluation': evaluate(total), 'source_hashes': sorted({r['file_sha256'] for r in rows}),
            'retrieved_at': sorted({r['retrieved_at'] for r in rows})}


def fmt(number, digits=2):
    return 'indisponible' if number is None else f'{number:,.{digits}f}'.replace(',', ' ').replace('.', ',')


def export_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def report(summary, output):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    output.mkdir(parents=True, exist_ok=True)
    latest, ipc = summary['credit_latest'], summary['cpi_latest']
    evaluation = summary['evaluation']
    credit = summary['credit_total'][-60:]
    fig = make_subplots(rows=2, cols=1, vertical_spacing=.20,
                        subplot_titles=('Crédit bancaire : encours mensuel', 'IPC national : variation annuelle'))
    fig.add_trace(go.Scatter(x=[r['period_start'] for r in credit], y=[r['value']/1000 for r in credit],
                            name='Crédit', mode='lines', line=dict(color='#156b72',width=3)),row=1,col=1)
    cpi = summary['cpi_general']
    fig.add_trace(go.Bar(x=[r['period_start'][:4] for r in cpi], y=[r['yoy_pct'] for r in cpi],
                        name='IPC', marker_color='#bb6537'),row=2,col=1)
    fig.update_yaxes(title_text='Milliards MAD',row=1,col=1)
    fig.update_yaxes(title_text='Variation (%)',row=2,col=1)
    fig.update_layout(height=670,template='plotly_white',showlegend=False,margin=dict(l=75,r=25,t=50,b=50),
                      font=dict(family='Arial',size=14),hovermode='x unified')
    charts = fig.to_html(full_html=False, include_plotlyjs=True, div_id='macro-series',
                         config={'responsive':True,'displaylogo':False})

    predictions = go.Figure()
    first = [r for r in evaluation['predictions'] if r['method']==METHODS[0]]
    predictions.add_trace(go.Scatter(x=[r['target_period'] for r in first],y=[r['actual_mdh']/1000 for r in first],name='Observé',line=dict(color='#173b4f',width=3)))
    for method in METHODS:
        points = [r for r in evaluation['predictions'] if r['method']==method]
        predictions.add_trace(go.Scatter(x=[r['target_period'] for r in points],y=[r['prediction_mdh']/1000 for r in points],name=LABELS[method],line=dict(dash='dot')))
    predictions.update_layout(template='plotly_white',height=430,yaxis_title='Milliards MAD',
        font=dict(family='Arial',size=14),hovermode='x unified',margin=dict(l=75,r=25,t=30,b=100),
        legend=dict(orientation='h',y=-.25))
    charts2 = predictions.to_html(full_html=False,include_plotlyjs=False,div_id='baseline-series',config={'responsive':True,'displaylogo':False})
    sector_rows = ''.join(f"<tr><th>{escape(r['category_label'])}</th><td>{fmt(r['value']/1000)}</td><td>{fmt(r['share_pct'])}</td><td>{fmt(r['yoy_pct'])}</td></tr>" for r in summary['credit_sectors'])
    division_rows = ''.join(f"<tr><th>{escape(r['category_label'])}</th><td>{fmt(r['value'],1)}</td><td>{fmt(r['yoy_pct'])}</td></tr>" for r in summary['cpi_divisions'])
    metric_rows = ''.join(f"<tr><th>{LABELS[r['method']]}</th><td>{fmt(r['mae_mdh'])}</td><td>{fmt(r['rmse_mdh'])}</td><td>{fmt(r['mase'],3)}</td></tr>" for r in evaluation['metrics'])
    attribution = ('Sources : Bank Al-Maghrib et HCP via data.gov.ma, licence ODbL. '
                   'Calculs dérivés : normalisation, parts et variations annuelles. '
                   'Les détails de provenance accompagnent les exports JSON et CSV.')
    html = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Radar macro-financier marocain</title><style>
body{{margin:0;background:#f4f6f5;color:#17313e;font:16px/1.6 Arial,sans-serif}}main{{max-width:1080px;margin:auto;padding:36px 24px}}
h1{{font-size:36px;line-height:1.15}}h2{{margin-top:40px;font-size:24px}}.eyebrow{{text-transform:uppercase;letter-spacing:.14em;font-size:12px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}.metric{{background:white;padding:20px;border-top:3px solid #156b72}}strong.value{{display:block;font-size:30px}}
small{{display:block;color:#46606b}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:12px;border-bottom:1px solid #dae1df}}th{{text-align:left}}td{{text-align:right;font-variant-numeric:tabular-nums}}
.table-wrap{{overflow-x:auto}}.note{{border-left:3px solid #bb6537;padding-left:16px}}a{{color:#146475}}footer{{margin-top:40px;border-top:1px solid #c6d3d1;padding-top:20px}}
@media(max-width:640px){{.metrics{{grid-template-columns:1fr}}main{{padding:20px 12px}}h1{{font-size:28px}}th,td{{padding:8px}}}}@media print{{body{{background:white}}main{{padding:0}}}}
</style></head><body><main><p class="eyebrow">Maroc · Portfolio data · Partie 3</p><h1>Radar macro-financier</h1>
<p>Crédit bancaire et prix à la consommation. Dernières périodes présentes dans les fichiers collectés ; fréquences distinctes.</p>
<div class="metrics"><div class="metric">Encours de crédit<strong class="value">{fmt(latest['value']/1000,1)} Md MAD</strong><small>{latest['period_start'][:7]} · BAM</small></div>
<div class="metric">Variation annuelle du crédit<strong class="value">{fmt(latest['yoy_pct'])} %</strong><small>{latest['period_start'][:7]} / même mois de l’année précédente</small></div>
<div class="metric">Variation annuelle de l’IPC<strong class="value">{fmt(ipc['yoy_pct'])} %</strong><small>{ipc['period_start'][:4]} · indice annuel national</small></div></div>
{charts}<h2>Répartition institutionnelle du crédit</h2><p>{latest['period_start'][:7]}. Trois groupes de premier niveau, sans addition de leurs sous-catégories.</p>
<div class="table-wrap"><table><thead><tr><th>Secteur</th><th>Milliards MAD</th><th>Part (%)</th><th>Variation annuelle (%)</th></tr></thead><tbody>{sector_rows}</tbody></table></div>
<h2>Prix par division de consommation</h2><p>National, {ipc['period_start'][:4]}. L’indice général est celui publié par le HCP ; aucune moyenne non pondérée des divisions n’est utilisée.</p>
<div class="table-wrap"><table><thead><tr><th>Division</th><th>Indice 2017 = 100</th><th>Variation annuelle (%)</th></tr></thead><tbody>{division_rows}</tbody></table></div>
<h2>Évaluation des méthodes de référence</h2><p>24 prévisions successives à un mois, de {evaluation['test_start'][:7]} à {evaluation['test_end'][:7]}. Chaque prévision utilise uniquement les périodes antérieures à sa cible. L’erreur la plus faible est préférable.</p>
<p class="note">{LIMITATION} Aucun modèle n’est sélectionné pour la production sur ce seul test.</p>{charts2}
<div class="table-wrap"><table><thead><tr><th>Méthode</th><th>MAE (MDH)</th><th>RMSE (MDH)</th><th>MASE</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
<p>MAE : erreur absolue moyenne. RMSE : pénalise davantage les grandes erreurs. MASE : MAE divisée par l’erreur du dernier mois calculée sur la période initiale d’apprentissage.</p>
<h2>Périmètre d’interprétation</h2><p>Les secteurs institutionnels BAM et les divisions de consommation HCP décrivent des populations différentes. Ils ne sont pas joints. Les données CNSS, les défauts d’entreprises et les expositions par branche ne sont pas disponibles dans ce lot : aucun score de risque de défaut n’est calculé.</p>
<footer><p>{attribution}</p><p><a href="https://data.gov.ma/data/dataset/data_i3981">Source HCP</a> · <a href="https://data.gov.ma/data/dataset/ventilation-du-credit-bancaire-par-secteur-institutionnel-dec-2001-a-sept-2023">Source BAM</a> · <a href="https://opendatacommons.org/licenses/odbl/1-0/">ODbL</a></p><small>Collecte UTC : {escape(', '.join(summary['retrieved_at']))}</small></footer>
</main></body></html>'''
    (output/'radar.html').write_text(html,encoding='utf-8')
    (output/'analysis.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    export_csv(output/'baseline_predictions.csv',evaluation['predictions'],list(evaluation['predictions'][0]))
    export_csv(output/'baseline_metrics.csv',evaluation['metrics'],list(evaluation['metrics'][0]))
    fields = ['source_id','period_start','category_label','value','unit','yoy_pct','source_url','file_sha256','sheet','cell','record_id']
    export_csv(output/'macro_indicators.csv',summary['credit_sectors']+summary['cpi_divisions']+[latest,ipc],fields)
    return output/'radar.html'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,default=ROOT/'data/prepared/indicators.jsonl')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/partie-3')
    args = parser.parse_args()
    payload = args.input.read_bytes()
    rows = [json.loads(line) for line in payload.decode('utf-8').splitlines()]
    summary = summarize(rows)
    summary['input_sha256'] = hashlib.sha256(payload).hexdigest()
    path = report(summary,args.output)
    print(json.dumps({'report':str(path),'metrics':summary['evaluation']['metrics']},ensure_ascii=False))


if __name__=='__main__':
    main()
