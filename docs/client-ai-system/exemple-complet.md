# Exemple complet — FORMAT v10.6 (mise en page terrain aérée, 17 juillet 2026 — le SKILL.md fait foi pour le détail des règles)

**La référence AUTHENTIQUE est l'événement vivant dans l'agenda** : le call ASNU77806 « MABL ajd 640-101 St-Jean: Évier bouché / Porte sdb / Prises brisées / Fuite clim », id `ckjuus9hc7cfp1l29laaddmobg`. En cas de doute sur le rendu, l'ouvrir et le comparer — il fait foi et se reproduit exactement. L'exemple ci-dessous en reprend la structure; les coordonnées d'occupants sont illustratives (toujours tirer les vraies du RRIA au moment du triage).

## Description type envoyée à l'API (vraies balises HTML, ajoutée AU-DESSUS de la requête originale)

```html
<b><u>FOLLOW-UP TERRAIN</u></b><br><br><br><br><br><br><br><br><br><b><u>PROBLÈMES :</u></b><br><br><b><br>1. [Item le plus urgent — reprendre TOUTE l'information de la requête, les mots du locataire, aucun détail coupé].</b><br><b><br>2. [Item suivant].</b><br><b><br>3. [Item suivant].</b><br><br><br><br><b><u>PERMISSION D'ENTRÉE</u> :</b> Autorisé en tout temps sans restriction<br><br><b><u>ANIMAUX</u> :</b> Non (conforme au bail)<br><br><b><u>OCCUPANTS</u> :</b><br>[Prénom Nom] — [tél] — [courriel]<br>[Co-titulaire s'il y a lieu — tél — courriel]<br><br><b><u>BAIL</u> :</b> 4 1/2 — début : 1er juillet 2026 — fin : 30 juin 2027 (emménagement récent)<br><br><b><u>FICHE TECHNIQUE</u> :</b> <a href="[lien pris EXCLUSIVEMENT dans la colonne E de la Table Fondamentale]">[nom de la fiche]</a><br><br><b><u>HISTORIQUE</u> :</b><br><a href="[htmlLink]">[appel 1 — le plus récent]</a> — [date, réglé/actif]<br>[appel 2 sans lien — date, réglé/actif]<br><br><br><br><br><b>================================================</b><br><b>================================================</b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b>================================================</b><br><b>================================================</b><br><br><b><u>SECTION COORDOS</u></b><br><br><b>TRI :</b> item 1 → règle vite · item 2 → reportable<br><br><b>DÉLÉGABLE :</b> NON<br><br><b>REPORT :</b> À la discrétion du superviseur<br><br><b>DOUBLONS :</b> Aucun<br><br><b>CALLS ACTIFS / SYNERGIE :</b><br><a href="[htmlLink]">[TITRE DU CALL 1 sans préfixe d'initiales]</a> — [date, précision de regroupement]<br><a href="[htmlLink]">[TITRE DU CALL 2 sans préfixe d'initiales]</a> — [date]<br>[CALL COMPACT sans initiales ni lien — date]<br><br><b>UNITÉ :</b> [numéro unique officiel]<br><br><b>PROJET :</b> [nom unique de projet]<br><br><b>TEMPS :</b> <30 min<br><br><b>COMPLEXITÉ :</b> C1 — n'importe qui<br><br><b>SOUS-TRAITANT :</b> Non — interne<br><br><b>ASSIGNATION PROPOSÉE :</b> [initiales de l'assigné]<br><br><b>ENTENTE LOCATAIRE POUR REPORT OU AUTRE :</b><br><br><b>AUTRES NOTES :</b><br>[signalement factuel bref]<br><br><b>EMBOURBEMENT :</b> N5 — critique<br><br>BÉLANGER 17 juillet 2026<br><br>----------------------------------------<br>[requête Gravity Forms originale conservée intacte ici]
```

## Ce qui fait la qualité de cet exemple (règles v10.6)

1. **FOLLOW-UP TERRAIN tout en haut** : titre seul, aucune explication, ~8 lignes vides — grande zone de saisie mobile.
2. **AUCUN titre « SECTION TERRAIN »** : après la zone FOLLOW-UP, la note enchaîne directement sur PROBLÈMES (v10.6). La zone terrain demeure comme concept — toutes les règles qui la nomment restent en vigueur.
3. **PROBLÈMES : items ENTIÈREMENT en gras, une ligne vide entre chaque, TROIS lignes vides après le dernier** — format `<b><br>N. [énoncé complet].</b><br>`. TOUTE l'information de la requête, les mots du locataire, aucun détail coupé; AUCUNE piste de solution (règle cardinale n° 20); triés du plus urgent au moins urgent, l'eau active toujours en tête. **Aucun montant d'argent.** Bloc PHOTOS APPAREIL (s'il y a un appareil) inséré immédiatement après le dernier item, les trois lignes vides tombant alors après lui.
4. **Libellés des blocs terrain gras + soulignés** (`<b><u>LIBELLÉ</u> :</b>`) : PROBLÈMES, PHOTOS APPAREIL, PERMISSION D'ENTRÉE, ANIMAUX, OCCUPANTS, BAIL, FICHE TECHNIQUE, HISTORIQUE. Les libellés de la SECTION COORDOS restent en gras simple.
5. **PERMISSION D'ENTRÉE en code sec** parmi les quatre codes standards; la mention « (traitement prioritaire) » du formulaire Gravity est ignorée à jamais.
6. **OCCUPANTS aéré + BAIL dense (v10.5)** : un occupant par ligne « Nom — tél — courriel » (TOUS les co-titulaires du RRIA — garde-fou bloquant), puis le bloc BAIL sur une seule ligne « grandeur — début : date — fin : date » avec « (emménagement récent) » si le bail a moins de 3 mois.
7. **FICHE TECHNIQUE = nom + lien pris exclusivement dans la colonne E de la Table Fondamentale**, rien d'autre.
8. **HISTORIQUE et CALLS ACTIFS / SYNERGIE : un élément par ligne, UN seul `<br>` entre chaque**; « Aucun » sec quand vide; **AUCUNE initiale d'employé nulle part dans ces blocs (règle cardinale n° 31)** — titres cités sans leur préfixe d'initiales, annotations « — date » sans nom. La SYNERGIE reste un inventaire EXHAUSTIF dans la filière du call (règles cardinales n° 11 et n° 13), maximum 5 entrées avec lien.
9. **SÉPARATEUR SANDWICH (v10.6)** avant SECTION COORDOS : quatre lignes vides, DEUX grosses lignes doubles en gras, SEPT lignes vides, puis DE NOUVEAU deux grosses lignes doubles — les gars de terrain ne descendent jamais là.
10. **TRI / DÉLÉGABLE / REPORT très courts**; REPORT du tout-venant = « À la discrétion du superviseur ». **DOUBLONS : « Aucun » sec** — jamais de description des recherches.
11. **SECTION COORDOS à 14 catégories dans l'ordre exact (inchangée en v10.6)** : TRI → DÉLÉGABLE → REPORT → DOUBLONS → CALLS ACTIFS / SYNERGIE → UNITÉ → PROJET → TEMPS → COMPLEXITÉ → SOUS-TRAITANT → ASSIGNATION PROPOSÉE → ENTENTE LOCATAIRE POUR REPORT OU AUTRE → AUTRES NOTES → EMBOURBEMENT.
12. **La requête originale du locataire reste intacte** sous le séparateur; signature `BÉLANGER + date`.

## Rappel — call multi-items (même unité = un seul call)

Titre : `3146-410 France-Prime: Robinet douche coule / Bain rouillé / Plancher salon` (sans initiales depuis le 13 juillet 2026 — l'assigné vit en ASSIGNATION PROPOSÉE)

Les catégories COORDOS se déclinent par volet quand les items n'ont pas le même poids, toujours en très court :
- `TRI : robinet → règle vite · bain rouillé → reportable · plancher → reportable`
- `REPORT : PAR VOLET — robinet non; bain + plancher : à la discrétion du superviseur`
- `TEMPS : robinet <30 min / bain-plancher : soumission requise`
- `COMPLEXITÉ : robinet C2 — ouvrier / bain-plancher C4 — sous-traitant`

Le titre, lui, reste intouchable : structure historique, items séparés par « / », aucune annotation de triage.
