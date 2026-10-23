"""Original fictional UI fixtures, not a model or category-quality evaluation."""
import argparse
from quillgrain.pairwise import GROUPS, common_input, make_session, words
from quillgrain.duel import ARMS, freeze
from quillgrain.io import digest, sha


def cases():
    result = []
    for i in range(30):
        source = (f'В вымышленной мастерской номер {i + 1} открыли полку для вещей, которые посетители забыли после занятий. '
                  'Раньше они лежали в коробке под столом, и администратор каждый раз вытаскивал её, когда кто-нибудь возвращался за своей вещью. '
                  'Теперь полку видно от входа. На ней стоят кружка с отбитой ручкой, блокнот без обложки и маленький фонарик. '
                  'Посетитель может попросить администратора показать находку, но забрать её можно только после разговора с ним. '
                  'Фотографий вещей в интернете нет. Новая полка не обещает вернуть всё потерянное: она просто помогает увидеть то, что уже принесли в мастерскую.')
        meaning = [dict(entity='Полка', relation='назначение', value='забытые после занятий вещи',
                        modality='asserted', evidence='полку для вещей, которые посетители забыли после занятий'),
                   dict(entity='Публикация фотографий', relation='наличие', value='нет',
                        modality='asserted', evidence='Фотографий вещей в интернете нет.')]
        c = dict(schema_version='duel.pair-case/v2', id=f'fictional-case-{i}', work_id=f'fictional-work-{i}',
                 group=GROUPS[i // 6], language='ru', source_text=source, source_sha256=sha(source.encode()),
                 purpose='Вымышленный пример для проверки парного интерфейса; не реальный материал категории.',
                 meaning=meaning, meaning_reviewed=True, overlap_reviewed=True,
                 rights={'local_use_reviewed': True, 'basis': 'Original synthetic fixture'},
                 editorial_audit={'status': 'REVIEWED', 'note': 'Mock fixture, no inference evidence.'},
                 provenance={'note': 'Original synthetic UI fixture; no external source.'}, authorship='synthetic', variants={})
        rewrites = [source,
                    source.replace('открыли полку', 'выделили отдельную полку'),
                    source.replace('Раньше они лежали в коробке под столом', 'До этого забытые вещи складывали в коробку под столом'),
                    source.replace('Теперь полку видно от входа.', 'Теперь вошёл — и сразу видишь полку.')]
        for arm, text in zip(ARMS, rewrites):
            v = dict(text=text, sha256=sha(text.encode()), words=words(text), status='ORIGINAL' if arm=='ORIGINAL' else 'MOCK')
            if arm != 'ORIGINAL':
                v.update(raw_text=text, model='synthetic', model_digest='not-a-model', runtime='fixture', options={},
                         seed=i, source_sha256=c['source_sha256'], brief_sha256=digest(meaning), common_input_hash=digest(common_input(c)))
            c['variants'][arm] = v
        result.append(freeze(c))
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out', required=True)
    a=parser.parse_args()
    make_session(cases(), a.out, order_seed=422, mapping_seed=903, synthetic=True)
    print('SYNTHETIC_PAIR_DEMO_READY: 30 mock rounds, no real model outputs.')
