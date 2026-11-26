from src.previsao.editorial.cinco import _ids_rodizio


def test_rodizio_cobre_todos_os_pontos_sem_repetir_ate_completar_ciclo():
    for total in range(1, 12):
        ids = tuple(str(i) for i in range(total))
        primeiros = [_ids_rodizio(ids, 100 + i // 2, i % 2)[0] for i in range(total)]
        assert set(primeiros) == set(ids)
        assert len(primeiros) == len(set(primeiros))
        assert _ids_rodizio(ids, 100, 0) == _ids_rodizio(ids, 100, 0)
