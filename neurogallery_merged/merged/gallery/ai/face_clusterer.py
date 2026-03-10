"""
gallery/ai/face_clusterer.py

Groups face encodings into clusters (= persons) using DBSCAN.
Each unique cluster gets / updates a Person record in the database.
"""
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.cluster import DBSCAN
    from sklearn.preprocessing import normalize
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not installed – clustering disabled.")


def cluster_faces(user):
    """
    Re-cluster ALL FaceEncoding rows belonging to *user*.

    Steps:
      1. Load encodings from DB.
      2. Run DBSCAN (eps=0.5, min_samples=2).
      3. Create / update Person records.
      4. Link each FaceEncoding to its Person.
      5. Return number of clusters found.
    """
    from gallery.models import FaceEncoding, Person

    if not SKLEARN_AVAILABLE:
        logger.warning("sklearn missing – skipping clustering.")
        return 0

    enc_qs = FaceEncoding.objects.filter(photo__user=user).select_related('photo')
    if enc_qs.count() < 1:
        return 0

    ids       = []
    encodings = []
    for fe in enc_qs:
        try:
            vec = json.loads(fe.encoding)
            encodings.append(vec)
            ids.append(fe.id)
        except (json.JSONDecodeError, TypeError):
            continue

    if len(encodings) < 1:
        return 0

    X = normalize(np.array(encodings, dtype=np.float64))
    # min_samples=1 ensures even a single face forms its own cluster (Person)
    labels = DBSCAN(eps=0.45, min_samples=1, metric='euclidean', n_jobs=-1).fit_predict(X)

    # Map cluster_id → Person
    cluster_person_map = {}
    existing = Person.objects.filter(user=user)
    for p in existing:
        cluster_person_map[p.cluster_id] = p

    unique_labels = set(labels) - {-1}
    n_clusters = len(unique_labels)

    for label in unique_labels:
        if label not in cluster_person_map:
            person = Person.objects.create(
                user=user,
                name=f'Person {label + 1}',
                cluster_id=label,
            )
            cluster_person_map[label] = person

    # Assign encodings → persons
    fe_map = {fe.id: fe for fe in enc_qs}
    for fe_id, label in zip(ids, labels):
        fe = fe_map.get(fe_id)
        if fe is None:
            continue
        if label == -1:
            fe.person = None
        else:
            fe.person = cluster_person_map[label]
        fe.save(update_fields=['person'])

    # Update photo_count on each Person
    for person in cluster_person_map.values():
        person.photo_count = (
            FaceEncoding.objects.filter(person=person)
            .values('photo').distinct().count()
        )
        # Assign thumbnail from first face encoding with a face_image
        first = FaceEncoding.objects.filter(person=person).exclude(face_image='').first()
        if first and first.face_image:
            person.thumbnail = first.face_image
        person.save()

    return n_clusters
