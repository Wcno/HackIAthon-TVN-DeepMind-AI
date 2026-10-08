"""Bind human decisions to the complete content they reviewed, across file exports."""

from whoami.schemas import OutputSet, ReviewArchive


def review_snapshots(output: OutputSet) -> dict[str, ReviewArchive]:
    cases = {case.id_caso: case for case in output.fichas}
    groups = {group.id_grupo: group for group in output.grupos}
    snapshots = {}
    for case_id in dict.fromkeys(record.id_caso for record in output.revisiones):
        case = cases[case_id]
        group = groups[case.id_grupo]
        ids = set(case.cited_ids) | {member.id_noticia for member in group.miembros}
        ids |= {link.id_evidencia for link in group.contexto}
        ids |= {version.id_evidencia for contradiction in case.contradicciones for version in contradiction.versiones}
        if group.cobertura_tvn:
            ids |= set(group.cobertura_tvn.ids_tvn)
        sources = {identity: output.evidencias[identity] for identity in ids}
        snapshots[case_id] = ReviewArchive(
            ficha=case, grupo=group, evidencias=sources,
            decisiones=tuple(record for record in output.revisiones if record.id_caso == case_id),
            contenido_sha256=ReviewArchive.digest(case, group, sources),
        )
    return snapshots


def bind_reviews(output: OutputSet) -> OutputSet:
    return output.model_copy(update={"revisiones_vinculadas": tuple(review_snapshots(output).values())})


def reconcile_reviews(output: OutputSet) -> OutputSet:
    """Retire file-based approvals whose saved content no longer matches the loaded inputs."""
    if not output.revisiones_vinculadas:
        return output  # Legacy files remain readable; regeneration requires a binding.
    current = review_snapshots(output)
    stale = {snapshot.ficha.id_caso for snapshot in output.revisiones_vinculadas
             if snapshot.contenido_sha256 != current[snapshot.ficha.id_caso].contenido_sha256}
    archives = list(output.historial_revisiones)
    for snapshot in output.revisiones_vinculadas:
        if snapshot.ficha.id_caso in stale and snapshot not in archives:
            archives.append(snapshot)
    return output.model_copy(update={
        "revisiones": tuple(record for record in output.revisiones if record.id_caso not in stale),
        "revisiones_vinculadas": tuple(snapshot for snapshot in output.revisiones_vinculadas
                                      if snapshot.ficha.id_caso not in stale),
        "historial_revisiones": tuple(archives),
    })
