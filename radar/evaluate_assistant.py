"""Functional regression set; not an independent semantic quality benchmark."""
import json
from pathlib import Path
from radar.assistant import ask, ROOT


def evaluate(index_path, cases_path, output):
    cases=json.loads(Path(cases_path).read_text(encoding='utf-8'))
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    results=[]
    demo=['# Démonstration de l’assistant local', '',
          'Réponses SQL calculées et passages PDF retrouvés. Sans LLM ni synthèse générative.', '',
          'Ce jeu vérifie les fonctions connues. Il ne mesure pas la pertinence sur des questions indépendantes.', '']
    for case in cases:
        answer=ask(index_path,case['question'])
        checks={'status':answer['status']==case['status']}
        if 'value' in case:
            checks['value']=abs(answer.get('value',float('inf'))-case['value'])<1e-6
        if 'min_citations' in case:
            checks['citations']=len(answer.get('citations',[]))>=case['min_citations']
        if 'expected_doc' in case:
            checks['retrieval']=any(c.get('doc_id')==case['expected_doc'] and c.get('pdf_page')==case['expected_page'] for c in answer['citations'])
        results.append({'id':case['id'],'passed':all(checks.values()),'checks':checks,'response':answer})
        demo += [f"## {case['question']}",'',answer['answer'],'']
        for citation in answer['citations']:
            if 'pdf_page' in citation:
                demo += [f"- [{citation['title']} — page PDF {citation['pdf_page']}, étiquette imprimée {citation['printed_page']}]({citation['url']})"]
            else:
                demo += [f"- [{citation['source_id']}]({citation['source_url']}) : feuille {citation['sheet']}, cellule {citation['cell']}, période {citation['period_start']}."]
        demo += ['']
    passed=sum(r['passed'] for r in results)
    report={'passed':passed,'total':len(results),'benchmark_type':'functional_regression_not_independent_relevance_evaluation','cases':results}
    (output/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'demonstration.md').write_text('\n'.join(demo),encoding='utf-8')
    print(json.dumps({'passed':passed,'total':len(results)}))
    if passed!=len(results):
        raise AssertionError(f'{passed}/{len(results)} functional checks passed')
    return report


def main():
    evaluate(ROOT/'data/assistant.sqlite', ROOT/'config/assistant-evaluation.json', ROOT/'outputs/partie-4')


if __name__=='__main__':
    main()
