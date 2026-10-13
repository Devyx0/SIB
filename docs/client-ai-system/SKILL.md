---
name: "nouvelle-demande-de-maintenance-triage-initial"
description: "Analyser un appel de service (call) de maintenance immobilière et le préparer dans l'agenda Google « Maintenance » de la Société Immobilière Bélanger (SIB), sans jamais le déplacer de date. Utiliser cette skill dès que l'utilisateur demande de traiter, analyser, préparer, trier, « dispatcher » ou « prendre » un call, un appel de service, ou une nouvelle demande (verte) de l'agenda — même s'il ne mentionne qu'une adresse ou une unité (ex. « prends le call du 3140-501 France-Prime », « traite les nouvelles demandes du samedi », « prépare l'appel de Costebelle »). S'applique aussi aux demandes de recherche de doublons, à l'enrichissement des notes de calls existants, et au TRIAGE AUTOMATIQUE relié au courriel — chaque nouvel appel de service vu lors du vidage de la boîte Gmail maintenance est traité automatiquement avec cette skill, silencieusement, sans rapport. S'applique aussi si le coordonnateur envoie une capture d'écran (call existant à identifier, ou courriel à créer) plutôt qu'une adresse tapée."
---

# Nouvelle demande de maintenance — Triage initial

**Format de note v10.6 · Guide coordonnateur v4.38 · Skill v6.1**

Historique des versions : le guide embarqué `references/guide-coordonnateur-maintenance-v4_38.md`. Ne jamais le lire pour exécuter un triage.

---

## 0. Principe directeur

Trier un appel de service, c'est produire trois choses dans l'agenda : un **titre** normalisé, une **note structurée** v10.6 ajoutée au-dessus de la requête intacte, et la **couleur du territoire**. Rien d'autre.

Une règle domine toutes les autres : **l'agenda fait foi de tout, toujours.** La Table Fondamentale, le RRIA, les fiches techniques, le tableau vivant enrichissent — ils ne contredisent jamais l'agenda. Écart entre une source et l'agenda : l'agenda gagne (réutiliser la couleur des calls précédents du même immeuble, ne jamais la « corriger »).

**Objectif d'exploitation : zéro accumulation.** Il ne doit jamais rester de demande verte non triée derrière soi.

---

## 1. ⛔ GARDE-FOUS ABSOLUS

Ces interdits ne souffrent aucune exception, aucune urgence, aucune charge de travail.

1. **Jamais supprimer** un événement. Même sur demande explicite : double confirmation avec rappel de cette règle.
2. **Jamais déplacer la date** d'un événement existant. Trois conditions cumulatives pour un déplacement : demande **explicite** du coordonnateur, visant **cet événement nommément**, donnée dans la **conversation en cours**. Une date reçue pour un événement ne se transfère JAMAIS à un autre, même connexe, même du même immeuble. À défaut : proposer, ne pas appliquer.
3. **Jamais écraser une description.** La note s'ajoute AU-DESSUS. La requête Gravity originale reste intacte en bas, toujours. Voir aussi la relecture obligatoire avant écriture (section 11).
4. **Jamais le gris** (`colorId 8`) — le gris veut dire « réglé », c'est une décision humaine. Appliquer la couleur du territoire n'a rien à voir avec régler un call.
5. **Notifications toujours `NONE`** sur chaque `update_event` et `create_event`.
6. **Jamais toucher** aux événements à préfixe `!` (administratif), `X` (en exécution), aux rouges (garde d'urgence) ni aux collectes de matières résiduelles.
7. **Jamais de vocabulaire interne dans un événement** — ni titre, ni note : `A1`-`A5`, `A3b`, « règle cardinale n° X », noms de skills, codes `C1`-`C4` / `N1`-`N5` hors des lignes COMPLEXITÉ et EMBOURBEMENT. Écrire l'action concrète en langage opérationnel simple.
8. **Signature `BÉLANGER + date`**, jamais « CLAUDE ».
9. **Jamais de montants d'argent** dans une note.
10. **Jamais de données financières du rent roll** (loyers, sommes dues, dépôts, endosseurs) dans un événement. Noms, téléphones, courriels, langue : permis.
11. **Jamais d'informations d'accès** dans une note (boîtes à clé, codes, emplacements de clés ou de valves) — la fiche technique liée s'en charge. Agenda visible par l'équipe et les sous-traitants.
12. **Jamais de courriel ni de brouillon Gmail** de sa propre initiative.
13. **Périmètre d'écriture strict** : le triage n'écrit QUE dans la nouvelle demande en cours. Deux exceptions balisées seulement (DOUBLON, AJOUT — section 8). Jamais modifier un autre événement de sa propre initiative.
14. **Aucun rapport** après un triage en session normale — travail courant et silencieux. Rapport sur demande explicite. (Session planifiée : court résumé d'exécution, section 13.1.)
15. **Anti-fabrication** — voir section 5. Un call dont le résultat d'outil n'est pas dans la conversation en cours **n'existe pas et ne s'écrit pas**.
16. **RRIA obligatoire** pour toute unité de logement — voir section 6. Garde-fou bloquant.
17. **Jamais deux verrous en même temps** — voir section 3. Une seule demande en traitement à la fois, du début à la fin.
18. **Le coordonnateur ne modifie jamais de code.** Tout Apps Script ou code livré l'est 100 % complet, clé en main, jamais un fragment.
19. **Bac à sable** : le samedi 4 juillet 2026 est l'environnement de test. Trier ses événements comme des calls normaux, mais ne jamais retoucher les originaux qu'ils dupliquent ailleurs.
20. **⛔ RÈGLE FONDAMENTALE — JAMAIS D'ASSIGNATION. JAMAIS.** Le triage n'assigne pas. Ni dans le titre, ni dans la note, ni nulle part.
    - **Jamais d'initiales dans le titre** : aucun préfixe, aucun suffixe, aucune initiale d'employé, de coordonnateur ou de fournisseur (pas de CHGE, ZARO, JFME, MACH, SAHA, CALE, PISI, SETO, ni aucune autre abréviation de personne).
    - **Le champ ASSIGNATION PROPOSÉE reste vide** — toujours, sans exception. Y inscrire des initiales, même « à titre de suggestion », c'est assigner. C'est une décision qui appartient exclusivement au coordonnateur, jamais au triage.
    - **Aucune exception**, aucune urgence, aucun cas particulier ne justifie de déroger à cette règle. Même si la catégorie A0-A5 désigne clairement un assigné, le champ reste vide — cette information guide le SOUS-TRAITANT et la logique de routage, elle ne se traduit jamais en initiales écrites dans un événement par le triage.

---

## 2. ⛔ RYTHME : ZÉRO ACCUMULATION, ATTERRISSAGE PROPRE

*Cette section remplace l'ancien garde-fou « traitement complet sans interruption ». Cette règle exigeait de continuer « peu importe le nombre d'unités, la durée de la session, ou toute autre contrainte perçue » — sans jamais dire comment s'arrêter autrement qu'en s'effondrant. Résultat observé : une session de 16 demandes ayant livré 2 notes, sans registre, avec perte complète de l'état de travail. L'ambition n'était pas le problème; l'absence d'atterrissage l'était.*

### 2.1 — La règle

**Enchaîner les demandes une à la fois, sans plafond pratique, jusqu'à ce que la file soit vide.** Une file longue n'est **JAMAIS** un motif d'arrêt. Ne jamais s'arrêter parce que « ça va être long », ni parce qu'il reste beaucoup d'appels.

**Plafond de sécurité : 30 demandes par exécution.** Au-delà de 30, ce n'est plus un volume normal — c'est le signe d'une anomalie (tâche à l'arrêt depuis des jours, afflux inhabituel, pont Gravity déréglé) qui mérite un signalement au coordonnateur plutôt qu'un traitement aveugle.

**S'arrêter uniquement sur un signal réel de dégradation**, jamais sur une estimation de la longueur de la file :

- échecs d'outil répétés sur le même appel;
- mémoire de travail visiblement saturée (résultats qui se déversent dans des fichiers à répétition, réponses tronquées);
- une même recherche qui ne converge pas malgré le resserrement de la clé (section 4.1).

### 2.2 — Protocole d'arrêt propre

Si un arrêt devient nécessaire, il se fait **proprement**, jamais par effondrement :

1. **Terminer l'appel en cours**, ou libérer son verrou et le laisser intact et vert (section 3.4).
2. **Aucune demande à moitié traitée** : à la fin d'une exécution, chaque demande est soit complètement triée, soit encore verte et intacte. Jamais entre les deux.
3. **Registre de progression à jour** (section 2.3).
4. **Résumé d'exécution** : nombre traité, nombre restant, raison de l'arrêt.
5. La prochaine exécution reprend **dans l'heure**, en commençant par le balayage des verrous abandonnés (section 3.3). Rien n'est perdu, rien n'est à refaire.

**Un arrêt propre avec reprise dans l'heure est un succès. Un effondrement sans livrable est un échec**, même en ayant suivi toutes les autres règles.

### 2.3 — Registre de progression

Obligatoire dès 2 appels dans une exécution. Écrire `progression-triage-[date].md` dans le dossier de sortie de la session, mis à jour **après chaque appel terminé** : id de l'événement, titre final, unité, verdict, faits clés retenus (RRIA, doublons, synergie).

Si la session redémarre ou perd son contexte, le registre est la source de reprise — jamais le transcript.

### 2.4 — Modèle et fréquence

**VERROU DE MODÈLE.** Le triage s'exécute dans **Sonnet** (réflexion moyenne) — la recherche est mécanique, un modèle plus coûteux n'y apporte rien. En session interactive : si le modèle courant n'est pas Sonnet, le signaler au coordonnateur et attendre sa décision avant de traiter (Claude ne peut pas changer de modèle lui-même). En **session planifiée**, le modèle fixé à la création de la tâche vaut autorisation permanente — ne jamais bloquer; mentionner une ligne au résumé s'il n'est pas Sonnet.

**FRÉQUENCE.** Les demandes Gravity entrent **en continu** et viennent se placer au samedi : la tâche se déclenche donc **aux heures, de 7 h à 17 h** (`0 7-17 * * *`), rien entre 18 h et 6 h. C'est viable parce qu'une exécution qui ne trouve aucune demande verte **ne coûte presque rien** : une seule recherche bornée, zéro résultat, arrêt immédiat, aucun rapport, aucune écriture. Ce qui est interdit, c'est le déclenchement 24 h sur 24 (`0 * * * *`) : il double les exécutions alors qu'aucune demande n'entre la nuit. Ce n'est jamais la fréquence qui coûte cher — ce sont les recherches non bornées de la section 4.

---

## 3. ⛔ VERROU : UNE SEULE DEMANDE À LA FOIS

*Le coordonnateur travaille dans l'agenda toute la journée et prend parfois une demande à la main quand il la juge urgente. Deux écritures simultanées sur le même événement produisent une perte silencieuse : le triage lit la description, écrit [note + description telle que lue], et efface au passage ce que le coordonnateur vient d'ajouter. Le verrou et la relecture (section 11) ferment cette porte.*

### 3.1 — Prendre le verrou

Avant toute recherche, avant toute lecture de RRIA, **première écriture sur la demande** :

- `update_event` : titre = `[EN TRAITEMENT] ` + titre d'origine conservé **verbatim**.
- **La couleur ne change pas** — la demande reste **verte** (`colorId 2`).
- **La date ne change pas.** Notifications `NONE`. **La description n'est pas touchée** à cette étape.

Pourquoi le vert est conservé : le vert est le seul discriminant fiable d'une demande non triée. Une demande dont la couleur changerait au moment de la prise, dans une session qui plante ensuite, deviendrait invisible à l'exécution suivante — orpheline pour toujours. En restant verte, elle demeure toujours trouvable. **La palette Google est par ailleurs entièrement utilisée chez SIB (11 couleurs sur 11), il n'existe aucune couleur libre pour un verrou.**

`[EN TRAITEMENT]` dit au coordonnateur : *vu, en cours, ne pas y toucher.*

### 3.2 — Un seul verrou à la fois

**Jamais deux demandes marquées simultanément.** Prendre le verrou, traiter au complet, libérer, et seulement là regarder la suivante. Le verrou ne reste posé que le temps d'un appel — quelques minutes.

### 3.3 — Balayage des verrous abandonnés (début de chaque exécution)

**Avant de chercher de nouvelles demandes**, chercher les demandes **vertes** dont le titre commence par `[EN TRAITEMENT]` :

- Marqueur posé depuis **moins de 15 minutes** → une autre exécution travaille peut-être dessus : ne pas y toucher.
- Marqueur posé depuis **plus de 15 minutes** → la session précédente a planté. Reprendre la demande : la traiter normalement au complet (le marqueur sera retiré à la libération).

Ce balayage est ce qui rend l'arrêt propre de la section 2.2 réellement sans perte.

### 3.4 — Libérer le verrou

**Sur succès** — dans le **même** `update_event` que la note finale : titre final **sans** `[EN TRAITEMENT]` (format de la section 11), note v10.6, **couleur du territoire**. Le marqueur disparaît naturellement.

**Sur abandon** (arrêt propre, appel non triable, blocage) : `update_event` qui **retire `[EN TRAITEMENT]`** et restaure le titre d'origine verbatim, demande **laissée verte et intacte**. Exception : l'appel non triable pour unité ambiguë reçoit son propre traitement (section 13.1, point 4) — le marqueur `[EN TRAITEMENT]` est alors remplacé par « Demande de clarification de l'adresse pour Triage ».

**Ne jamais laisser un marqueur derrière soi.** Un verrou non libéré est un appel qui a l'air pris en main alors que personne ne s'en occupe.

### 3.5 — Convention d'équipe

`[EN TRAITEMENT]` n'a de valeur que si les coordonnateurs savent ce qu'il veut dire. Cette convention doit être communiquée à l'équipe par le coordonnateur — pas par Claude (garde-fou 12 : jamais de courriel de sa propre initiative).

---

## 4. ⛔ MÉTHODE DE RECHERCHE

*L'ancienne méthode — recherche non bornée, sur deux agendas, paginée jusqu'à la dernière page, répétée pour chaque appel — était structurellement inachevable : une série récurrente d'entretien courant jusqu'en 2040 remplit des pages entières d'événements sans rapport, et l'obligation de paginer jusqu'au bout empêchait toute conclusion.*

### 4.1 — Bornage obligatoire

**Aucun `list_events` sans `startTime` ET `endTime`.** Une recherche non bornée est une erreur de méthode au même rang qu'un lien fabriqué.

| Recherche | Fenêtre |
|---|---|
| Nouvelles demandes vertes à trier | aujourd'hui → aujourd'hui + 7 j, **samedis seulement**, `colorId: "2"`, agenda principal uniquement |
| Verrous abandonnés | aujourd'hui − 2 j → aujourd'hui + 7 j, `colorId: "2"`, agenda principal |
| Doublons (unité exacte) | date de l'événement en triage − 90 j → + 45 j |
| Synergie (projet) | date de l'événement en triage − 60 j → + 21 j |
| Historique d'unité | date de l'événement en triage − 6 mois → + 21 j |

Les fenêtres de doublons, synergie et historique sont ancrées sur **la date de l'événement en triage**, jamais sur la date du jour.

`pageSize: 25`. **Pagination : jusqu'à la dernière page de la requête bornée.** Si une requête bornée dépasse 2 pages, la clé est trop large — resserrer (unité exacte plutôt qu'adresse, immeuble plutôt que projet), ne pas continuer à paginer.

### 4.2 — Exclusions mécaniques, avant toute analyse

Écarter des résultats, sans les examiner :

- **Tout événement issu d'une série récurrente**, peu importe la fréquence (abris d'hiver, inspection incendie, tapis, compresseur, batteries, lavage de fenêtres, listes administratives). Ce ne sont jamais des doublons ni de la synergie réelle.
- Les collectes de matières résiduelles.
- Les événements administratifs (préfixe `!`) et les listes d'immeubles.
- L'appel en cours de triage lui-même.

### 4.3 — Fichier maître des unités : UNE lecture par session

Le RRIA est découpé en une centaine de fichiers-blocs par projet — les lire un par un pour trouver une unité coûte des dizaines de milliers de caractères par ligne utile. **Chaque bloc porte en pied de page l'ID de son fichier source, qui est le même pour tous : c'est un fichier maître unique contenant toutes les unités de tous les projets.**

**Procédure obligatoire, une fois par session :**

1. Lire le fichier **« RRIA — 0 INDEX »** (`1AFE019j2gt_AqfI2PQgAsD9GixfCvXV56d7LEH0GMSw`) — il liste tous les fichiers de projet avec leur nombre de lignes.
2. Identifier l'**ID du fichier source maître** en pied de page de n'importe quel bloc (champ « Fichier source (ID) »).
3. Lire ce fichier maître **une seule fois**, l'écrire dans le sandbox, puis **interroger localement** (grep / python) pour chaque unité de l'exécution.
4. Vérifier la fraîcheur au champ « Généré le » — plus de 24 h = le signaler au coordonnateur.

Ne jamais lire les blocs de projet séquentiellement en espérant tomber sur la bonne unité. Si le fichier maître est inaccessible, alors seulement : lire le bloc du projet identifié par l'INDEX, et confirmer une absence avec `download_file_content` (décodage base64 en **une seule** commande autocontenue, jamais un pipeline multi-appels).

### 4.4 — Recherche groupée par projet

Le **verrou** est toujours un-à-la-fois (section 3), mais la **recherche** se mutualise : plusieurs demandes du même projet ne se recherchent qu'une fois.

1. Après avoir identifié la file, noter l'unité et le projet de chaque demande (Table Fondamentale).
2. **Une seule** passe de recherche par projet (doublons + synergie + historique, sur les deux agendas, bornée), **une seule** lecture de fiche technique, **une seule** interrogation du fichier maître pour toutes les unités du projet.
3. Puis traiter les demandes une à une, verrou par verrou, en réutilisant la recherche du projet.

Refaire la même recherche pour deux appels du même projet est une erreur de méthode.

### 4.5 — Délégation de la recherche à un sous-agent

Quand la file compte **2 demandes ou plus**, la recherche par projet se **délègue à un sous-agent** (outil Agent, modèle Sonnet ou Haiku), un par projet, lancés en parallèle.

Le sous-agent reçoit : le nom du projet, les unités concernées, les dates des événements en triage, les deux `calendarId`, les fenêtres de la section 4.1 et les exclusions de la section 4.2.

Il retourne **un rapport court et structuré** — jamais des résultats bruts :

```
PROJET : [nom]
FICHIER MAÎTRE — [unité] : nom, téléphone, courriel, co-titulaires, grandeur,
                 début et fin de bail, animaux au bail, électros SIB, statut
DOUBLONS : Aucun | [titre verbatim sans initiales] — [date] — [htmlLink] — [agenda]
SYNERGIE (max 5 avec lien, filière applicable) :
  [titre verbatim sans initiales] — [date] — [htmlLink] — [agenda]
  ... puis les compactes : [titre] — [date]
HISTORIQUE 6 MOIS (antéchronologique, max 3 liens) :
  [titre verbatim sans initiales] — [date] — réglé/actif — [htmlLink] — [agenda]
FICHE TECHNIQUE : [nom] — [lien colonne E de la Table Fondamentale]
PAGES LUES : [n] par recherche · dernière page atteinte : oui/non
```

**Les `htmlLink` retournés par le sous-agent sont des résultats d'outil réels et satisfont la règle anti-fabrication** — le sous-agent doit les copier tels quels de ses propres appels `list_events`/`get_event` et n'a pas le droit d'en composer un seul. Un rapport dont un lien est fabriqué est rejeté : relancer la recherche.

C'est cette délégation qui rend une longue file soutenable : la mémoire de travail reste disponible pour l'écriture des notes.

### 4.6 — Périmètre : les deux agendas d'appels de service

| Agenda | `calendarId` |
|---|---|
| MAIN - Calls (principal, atterrissage Gravity) | `maintenance@sibelanger.com` |
| MAIN - Calls ST Majordome Québec (rive-sud) | `8d55093fb316f4eda1504cd853462fea86f64a4e78556e0924f3c994d2c63bf8@group.calendar.google.com` |

**Recherche** : doublons, synergie et historique se relancent sur les deux, mêmes clés, mêmes fenêtres. Aucun verdict avant que les deux aient répondu. Un agenda qui retourne une erreur se traite comme « aucun résultat », et le fait se note au rapport.

**Exception** : la recherche des nouvelles demandes vertes et des verrous abandonnés reste sur l'agenda principal seulement.

**Synergie** : les calls de ST Majordome sont **fusionnés** à la synergie interne (même inventaire, même plafond de 5 liens), avec marqueur d'agenda source en fin d'entrée — `[agenda ST Majordome]`. Ce sont des dérivations de dispatch, pas des filières étanches.

**Historique** : une seule liste antéchronologique fusionnée sur les deux, jamais deux listes. Plafond de 3 liens tous agendas confondus, même marqueur.

**Doublons** : un doublon logé dans un autre agenda se traite comme un doublon interne. **L'appel original n'est jamais modifié.**

**Écriture** : autorisée dans les deux agendas. L'autorisation lève la lecture seule — elle n'élargit pas le périmètre d'écriture du garde-fou 13.

**Initiales** : les préfixes `MACH` se retirent à la citation comme tout préfixe d'initiales. Le marqueur d'agenda source, lui, s'écrit — c'est un nom d'agenda, pas une initiale d'assigné.

### 4.7 — Tableau vivant (accélérateur optionnel)

Le Sheet `1VLLHbK0euh-6utsGhI5XZSxmFdxQM4xrj9Ns69_OjAQ` (« Tableau des Appels de Service (IA) », onglet « Appels », régénéré aux 15 min, ~6 mois) peut servir à **identifier** des candidats : dédupliquer par ID Événement (doublons connus), vérifier la fraîcheur (colonne « Dernière modif agenda » — écart > 30 min = périmé), filtrer par la colonne Projet (colonne Y).

Il **n'est jamais une source de lien** : sa colonne « Lien événement » contient des liens « primary » impropres. Le lien final vient toujours du `htmlLink` de l'agenda. Tableau périmé ou vide : passer directement aux recherches bornées de la section 4.1.

---

## 5. ⛔ RÈGLE ANTI-FABRICATION

Toute référence à un call dans une note — SYNERGIE, DOUBLONS, HISTORIQUE — provient d'un **résultat d'outil obtenu dans la conversation en cours** (la sienne ou celle d'un sous-agent de la section 4.5) :

- **Titre** : copié verbatim de l'événement. Seule altération permise, et elle est obligatoire en SYNERGIE et HISTORIQUE : **retirer le préfixe d'initiales d'assigné**. Le corps du titre reste intact.
- **Date** : lue dans l'événement.
- **Lien** : le champ `htmlLink`, **copié tel quel**.

**Interdit** : composer une URL à la main, encoder soi-même un `eid`, utiliser le suffixe « primary », reconstituer un titre ou une date de mémoire — y compris de mémoire d'une recherche antérieure dans la même session. C'est le résultat d'outil qui fait foi, pas le souvenir.

**Contrôle avant chaque `update_event`** : chaque lien de la note est un `htmlLink` copié d'un résultat d'outil visant **l'un des deux `calendarId` autorisés**. En cas de doute : décoder en base64 la portion `eid=` du lien — elle contient « [eventId] [calendarId] » — et vérifier que le calendarId lu est l'un des deux.

⚠️ **L'ancien test du suffixe unique `...bWFpbnRlbmFuY2VAc2liZWxhbmdlci5jb20` est ABROGÉ comme test exclusif** : il invalide mécaniquement tout lien légitime de ST Majordome, dont les `eid` encodent leur propre calendarId. Il reste un indice valide pour l'agenda principal seulement.

**Aucune initiale d'employé, de coordonnateur ou de fournisseur** dans les blocs SYNERGIE et HISTORIQUE — les employés retrouvent leur charge en cherchant leurs initiales, et la recherche `fullText` fouille les descriptions : chaque initiale écrite dans une note crée un faux positif permanent.

---

## 6. ⛔ RRIA — GARDE-FOU BLOQUANT

Dossier « Rent roll (IA) » dans Mon Drive de maintenance@, régénéré chaque nuit vers 4 h. Un fichier par projet, blocs suffixés (2), (3)… au-delà de 90 occupants. Aucune donnée financière.

**Pour chaque unité de logement, la consultation est obligatoire avant l'envoi de la note.** Une note dont le bloc OCCUPANTS n'a pas été rempli à partir d'une lecture réelle **ne peut pas** être envoyée. La charge de travail, le nombre d'unités, ou l'intention de « valider après coup » ne sont jamais des motifs. Espaces communs exemptés.

La mention « RRIA non consulté — à valider par le coordonnateur » n'est acceptable que si le fichier est **objectivement inaccessible ou introuvable** après recherche — jamais par manque de temps.

**Lecture : par le fichier maître, section 4.3.**

**En tirer** : tous les occupants et co-titulaires (nom, téléphone, courriel), grandeur, début de bail (les dates entre parenthèses sont les débuts historiques), fin de bail, langue (mentionnée seulement si anglais), animaux au bail (croiser avec la déclaration Gravity — écart en AUTRES NOTES), électros fournis par SIB (un électro qui n'est pas de SIB n'est pas notre réparation — le signaler), meubles, statut et disponibilité (fin de bail proche ou relocation en cours = AUTRES NOTES; bail de moins de 3 mois = « emménagement récent »).

**Vérifier que le réquérant est au bail** — nom ou téléphone absent = signalement en AUTRES NOTES. Le réquérant n'est pas toujours titulaire.

**Résolution d'unité ambiguë par le RRIA.** Avant de déclarer un appel non triable pour numéro d'unité ambigu ou introuvable : chercher le **nom du réquérant** (et son téléphone) dans le fichier maître. Une correspondance **unique**, cohérente avec **tous** les indices partiels disponibles (un « 4 » au titre = l'unité trouvée doit contenir ce 4), **résout** l'unité — triage complet normal, déduction documentée en AUTRES NOTES (« Unité résolue par RRIA : réquérant [nom] trouvé à l'unité [unité] »). Ce n'est pas deviner, c'est une déduction vérifiée dans la source officielle. Zéro correspondance, correspondances multiples, ou incohérence avec un indice = appel réellement non triable (section 13.1, point 4).

---

## 7. Étape 1 — Constituer la file, puis prendre le premier verrou

1. **Balayage des verrous abandonnés** (section 3.3) — toujours en premier.
2. **Nouvelles demandes vertes** : `list_events` sur l'agenda principal, fenêtre aujourd'hui → aujourd'hui + 7 j, ne retenir que les **samedis**, filtrer sur `colorId: "2"`. La couleur verte est le **seul** discriminant fiable d'une demande non triée (les titres triés ne portent plus d'initiales). Une demande Gravity apparaît le samedi *suivant* sa soumission. Fenêtre vide = « aucune nouvelle demande » : arrêt silencieux, aucun rapport.
3. Extraire pour chaque demande : numéro d'unité, adresse, réquérant, téléphone, nature du problème, ASNU. Noter le projet de chacune.
4. **Recherche groupée par projet** (section 4.4), déléguée si 2 demandes ou plus (section 4.5).
5. **Prendre le verrou de la première demande** (section 3.1), puis la traiter au complet jusqu'à libération. Ensuite la suivante. Une seule à la fois, jusqu'à ce que la file soit vide (section 2.1).

---

## 8. Étape 2 — Doublon, ajout, ou demande unique

Les locataires soumettent souvent la même demande 2 à 5 fois. Comparer la **nature du problème**, pas seulement l'adresse. Même téléphone sur deux appels = signal fort.

**DOUBLON = même unité ET même problème** (peu importe la formulation).
→ Traitement complet normal de la nouvelle demande. **Ne jamais modifier l'appel original.** Ligne DOUBLONS : la raison en quelques mots + lien cliquable. **Titre de la nouvelle demande : mention `DOUBLON POTENTIEL` en majuscules, directement après le numéro d'unité et le deux-points** — `UNITÉ ADRESSE: DOUBLON POTENTIEL — Résumé court`. C'est une information qui doit sauter aux yeux en vue agenda. Fusion, renommage de l'original, grisage : décisions humaines exclusivement.

**AJOUT À APPEL ACTIF = même unité, problème DIFFÉRENT**, alors qu'un appel non gris existe pour l'unité. Ce n'est **pas** un doublon — le mot « doublon » n'apparaît nulle part.
→ **Vérifier d'abord la table d'attribution (section 10).** Catégorie A1-A4 = **pas de fusion** : appel autonome routé selon la table, l'appel actif de l'unité en première ligne de la SYNERGIE avec la mention « même unité — appel actif », plus un signalement en AUTRES NOTES. Le routage par catégorie prime sur la consolidation de visites.
→ Sinon, mécanique balisée : **(a)** l'information intégrale de la nouvelle requête (mots du locataire, ASNU, réquérant, téléphone) s'ajoute en **nouvel item numéroté à la suite** des items existants du bloc PROBLÈMES de l'appel actif — juste avant PERMISSION D'ENTRÉE, jamais au-dessus de toute la note — au format `N. AJOUT (ASNU#####, date) — [problème, mots du locataire]`, sans piste de solution, signature `BÉLANGER + date` dans l'item. FOLLOW-UP TERRAIN reste le tout premier bloc, sans exception. **(b)** Titre de l'appel actif ajusté : mention `AJOUT`, nouvel item au résumé (séparés par « / »), montée d'urgence `AJD`/`ajd` si le nouvel item l'exige. **(c)** La nouvelle demande renommée `UNITÉ ADRESSE: Ajout à appel existant`, description = note explicative + lien vers l'appel actif + requête Gravity intacte, **conservée à sa date**, couleur du territoire, jamais grisée.

Deux demandes vertes simultanées de la même unité : un seul call multi-items conservé (jamais scinder), l'autre référencée en « Ajout à appel existant ».

**Demande unique** → continuer.

### Les lentilles de synergie

- **Même problème, plusieurs unités = panne d'immeuble probable.** Chauffage, eau chaude, internet, intercom, ascenseur, buanderie, infiltration : 2+ unités du même immeuble sur le même sujet dans une fenêtre rapprochée = problème à la **source**. Le signaler, recommander un call racine traitant la cause, référencer les appels entre eux.
- **Synergie par filière** (fondamentale — la SYNERGIE ne mélange jamais les filières) :
  - **Appel interne** (employés SIB et ouvriers assimilés) : inventaire du projet, **sous-traitants exclus** (Duclos, Body Gym, Éric, 4 Saisons, Électro DB, Fortin, Newtech…). **Exception** : les calls de l'agenda ST Majordome sont fusionnés à l'inventaire interne.
  - **Appel attitré à un sous-traitant** : uniquement les autres appels du **même** sous-traitant, actifs ou sous garantie, immeuble puis projet. Un appel Duclos ne se synergise qu'avec Duclos.
  - **Extermination** (fourmis, blattes, souris, rats, guêpes, punaises, poissons d'argent) : la ligne est **exclusive** aux dossiers d'extermination du même immeuble puis du même projet, actifs **et sous garantie** (les titres du type « Éric (nov 2026) » indiquent une garantie en cours), en incluant les événements futurs. Aucun autre corps de métier : c'est le passage de l'exterminateur qu'on optimise. Deux unités avec la même vermine = colonie ou source d'immeuble probable — le noter en AUTRES NOTES et recommander un traitement à la source dans le même passage.
- **Inventaire exhaustif dans la filière, jamais une sélection au jugement.** Un call déjà assigné avec une date ferme se liste aussi — c'est la meilleure occasion de regroupement, pas une raison de l'écarter.
- **Samedis neutralisés.** Une demande verte atterrit au samedi et y reste jusqu'à ce qu'un humain la déplace. Deux appels tous deux encore datés un samedi ne partagent **pas** une date de visite réelle : la proximité de date ne compte jamais quand la date comparée est un samedi — la priorité retombe sur l'immeuble et le corps de métier. Ne jamais présenter un samedi partagé comme argument de synergie.

---

## 9. Étape 3 — Évaluer : urgence, puis TRIER · DÉLÉGUER · REPORTER

Lire la requête au complet : problème, permission d'accès, animaux, coordonnées, contraintes.

**Photos de la requête** : chercher le courriel Gravity par son ASNU dans maintenance@ (`search_threads` avec « ASNU##### », puis `get_message` pour les pièces jointes). Vérification faite **même si** la requête ne mentionne pas de photo. S'il y a des pièces jointes : mention **uniquement en AUTRES NOTES** — « N photo(s) jointe(s) à la requête ASNU##### — voir le courriel dans maintenance@ ». **Jamais dans PROBLÈMES.** Aucune pièce jointe = **silence complet**, aucune mention nulle part. Courriel introuvable = ne jamais bloquer.

### Urgence

- **AJD** (aujourd'hui non négociable) : eau qui coule activement — **y compris ses signes indirects : bruit de goutte d'eau dans un mur, tache d'humidité qui s'agrandit, plafond qui gondole = fuite cachée probable = AJD, même sans eau visible** —, refoulement, panne de chauffage ou d'eau chaude, personne coincée, alarme ou incendie, serrure non fonctionnelle, frigo mort, danger électrique ou structural.
- **ajd** (urgent si possible aujourd'hui) : fuite lente contenue, moisissure, électro défectueux non critique, **vermine — toute infestation signalée, sans exception**, climatisation en canicule.
- **Sans mention** : clés, puces, moustiquaires, esthétique, délais prolongés.

**Ce verdict s'écrit toujours dans le titre.** L'absence de mention est un **verdict** (call jugé non urgent), jamais un oubli : un AJD invisible est un AJD qui ne se fait pas aujourd'hui.

### Le fondement : trois questions dans l'ordre

Tout call non urgent passe par les trois — c'est la job n° 1 du coordonnateur, et Claude la lui prépare. L'ordre TRI → DÉLÉGABLE → REPORT dans la note **est** l'ordre du raisonnement.

1. **TRIER — décomposer en items.** Une demande = souvent 2-3 items empilés. Verdict par item : `règle vite` / `délégable` / `reportable`. Régler une partie du call rapidement est déjà une victoire. La clarification à 100 % fait souvent tomber des items d'eux-mêmes.
2. **DÉLÉGUER — au locataire ou à ses proches, dépenses remboursées.** Achats minimes et travaux mineurs (typiquement C1) : clés à tailler, pôle de douche, support à papier, petite peinture, petites poses. **Les clés mécaniques sont le cas parfait : DÉLÉGABLE OUI par défaut** — l'idéal est que les locataires se fassent un trousseau entre eux, au pire avec un léger frais remboursé. **Exception : les puces électroniques, jamais délégables** (Carmichael n'a pas de puces). Contexte favorable : l'emménagement récent. Jamais délégable : plomberie sous pression, électricité, structure, tout C3-C4. C'est une **offre**, jamais une pression — un refus se note sans commentaire. Locataire qui veut être payé : à N3+ on tend à dire oui, à N1-N2 moins.
3. **REPORTER — selon l'embourbement.** À N3+, tout le non-urgent se négocie vers plus tard, **avec l'accord du locataire, jamais dans son dos**. Le truc en or : proposer de clarifier la demande au complet et demander s'il y a « d'autres petites choses à regarder en même temps » — des items tombent, la bonne foi s'installe, la visite unique future règle tout. **Jamais reportable** : sécurité, AJD/ajd, rendez-vous fournisseur pris, échéances Ville ou légales, relances multiples (risque TAL), vacants avec emménagement. **L'accès autorisé n'est jamais un argument de report.** Ne jamais écrire « mode REPORTER activé ».

### Échelle d'EMBOURBEMENT (documentée ici, jamais expliquée dans une note)

| Niveau | Libellé | Effet sur le triage |
|---|---|---|
| N1 | Au-dessus de nos affaires | Réponse rapide, peu de délégation |
| N2 | Niveau courant | Rythme normal |
| N3 | En retard | Report négocié du non-urgent, délégation offerte activement |
| N4 | Très en retard | Report maximal, délégation payée volontiers |
| N5 | Critique | Tout ce qui peut attendre attend; délégation et sous-traitance sans hésiter |

**État actuel : N5 — critique.** S'inscrit en dernière ligne de la SECTION COORDOS, format sec.

---

## 10. Étape 4 — Attribution, territoire, unité, projet

**Vérifier les périmètres dédiés (A5) en premier — ils priment sur tout choix territorial.** Sinon : identifier le secteur par l'adresse, appliquer sa couleur, choisir l'employé du secteur disponible avec la spécialité qui colle. Tables complètes des couleurs, secteurs, employés et fournisseurs : `references/secteurs-et-equipe.md`.

### Attribution automatique par catégorie — à consulter avant la logique territoriale

**A0 — Coordonnateur par défaut : CHGE (Charles Genest), pour tous les cas.** Dès qu'un call requiert un coordonnateur SIB comme responsable (coordination d'un sous-traitant, dossier administratif, call sans employé terrain évident), c'est CHGE. Les autres (CALE, PISI, SETO) et la direction (CHBE) seulement sur directive explicite.

| # | Catégorie | Attribution | Application |
|---|---|---|---|
| A1 | **Complexité C1** — dépôts de manettes ou de clés, étiquette d'intercom, remises simples | **CHGE** | Peu importe le secteur — exception à la logique territoriale. Le call reste coté C1. |
| A2 | **Appareils de gym / salle d'entraînement** | **Body Gym** | Seul sous-traitant gym, sans évaluation interne préalable. C4. Assignation : CHGE, Body Gym en SOUS-TRAITANT. |
| A3 | **Portes/fenêtres — remplacement CERTAIN** : (a) évident dès la requête (vitre cassée, thermos éclaté ou embué, porte défoncée, cadre arraché, tout travail du verre) ou (b) confirmé par un diagnostic interne déjà fait | **Duclos** | Seul sous-traitant portes/fenêtres. Duclos ne reçoit un call que si le remplacement est certain — jamais sur un symptôme à cause inconnue. C4. |
| A3b | **Portes/fenêtres — cause INCONNUE** : ne s'ouvre pas, ne ferme pas, coince, difficile, courant d'air, bruit | **Homme de maintenance du secteur — DIAGNOSTIC D'ABORD** | Jamais Duclos directement, jamais la direction. Diagnostic sur place (C2), règle si c'est un ajustement simple; si le diagnostic confirme un remplacement → transfert à Duclos (devient A3). |
| A4 | **Catégories du coordonnateur par défaut — liste STRICTE, au libellé** : odeur de cigarette · intercom · alarme incendie · panneau d'alarme · avertisseur de fumée · clés de cadenas · manette · extermination (double assignation avec Éric) · collecte d'encombrants et gros meubles qui traînent · odeur de chute à déchets · trouble d'ascenseur ou de monte-charge · Bell · Vidéotron · Internet · trouble d'électroménager · neige · gazon · entretien extérieur · lavage des fenêtres · propreté des immeubles · état de la surface du stationnement (trou, nid de poule, asphalte) · élagage et végétation (arbre mort, branches cassées, arbustes, haies) | **CHGE (A0)** | CHGE est le **filtre humain initial** : il règle ou redispatche lui-même — ne jamais pré-redispatcher. Fournisseur nommé en ligne SOUS-TRAITANT quand la catégorie l'exige (extermination = CHGE + Éric). **(1)** La liste donne l'**assignation** seulement : l'urgence s'évalue normalement (alarme qui sonne, personne coincée, frigo mort = AJD, assigné CHGE, placé aujourd'hui). **(2)** Interprétation **stricte au libellé** : « lavage des fenêtres » = entretien → CHGE, mais une fenêtre à réparer reste A3/A3b. Doute = triage normal ou demander. |
| A5 | **Attributions dédiées par immeuble, projet ou territoire** — tous les appels du périmètre, peu importe la catégorie : (a) 350 ch. Ste-Foy, tout l'immeuble; (b) projet Chamonix / Sully; (c) rive-sud de Québec — Lévis, Charny (territoire orange) | **(a) JFME** · **(b) SAHA** · **(c) MACH** | L'employé dédié remplace le choix par secteur **et** le routage A4 : dans son périmètre, c'est lui le filtre humain local (JFME habite au 350). Les sous-traitants exclusifs demeurent : l'employé dédié est l'assigné et coordonne le sous-traitant, nommé en ligne SOUS-TRAITANT. Non-fusion limitée aux A1-A4. |

**Pas de fusion pour les catégories automatiques** : une demande A1-A4 produit toujours un appel autonome, jamais un « Ajout à appel existant ». **Seul le coordonnateur ajoute des règles à cette table** — Claude peut proposer une catégorie candidate quand un pattern ressort, jamais l'appliquer avant officialisation.

### Règles d'assignation — information pour le coordonnateur, jamais écrite par le triage

La table A0-A5 guide le raisonnement de routage. Elle informe la ligne SOUS-TRAITANT. **Elle ne se traduit jamais en initiales dans ASSIGNATION PROPOSÉE** — ce champ reste vide (garde-fou 20).

1. **Le secteur prime sur la spécialité** pour tout C1 ou C2 : un employé du secteur avec le mode d'emploi bat un spécialiste qui traverse la ville — le déplacement coûte plus que la tâche. La spécialité ne l'emporte qu'en C3-C4.
2. **Vérification négative obligatoire** : l'employé envisagé a-t-il travaillé dans ce secteur ou ce projet dans les 6 derniers mois? Si son nom n'y apparaît jamais, il n'y travaille probablement pas — ne pas l'assigner.
3. **Employé ambigu** : la décision reste au coordonnateur — le champ ASSIGNATION PROPOSÉE demeure vide. Mettre 1-2 candidats en AUTRES NOTES si pertinent pour informer le coordonnateur.

### Échelle de COMPLEXITÉ (documentée ici, jamais expliquée dans une note)

| Code | Libellé | Définition |
|---|---|---|
| C1 | N'importe qui | Aucun outil ni connaissance; bassin naturel des délégations |
| C2 | Ouvrier | Coffre standard, formation limitée |
| C3 | Ouvrier expérimenté / spécialité | Diagnostic, système d'immeuble |
| C4 | Sous-traitant / expertise externe | Newtech, Fortin, toiture, ascenseur, émaillage, extermination, soumission |

Format sec : `C2 — ouvrier`. Jamais de parenthèse, de conditionnel ni de référence de règle. **Sans surclasser** : programmer une étiquette d'intercom = `C1 — n'importe qui`.

### Sources — ordre de résolution

Les fichiers des connaissances du projet (`/mnt/project/`) ont préséance quand ils sont accessibles. Hors projet (tâche planifiée), les copies embarquées dans `references/` de cette skill font foi.

- **Table Fondamentale** — fichier `Table_Fondamentale__IMMEUBLES_PROJETS_ET_TERRITOIRES.xlsx`, copie contrôlée uniquement (projet ou `references/`), lue avec pandas/openpyxl. Colonnes A-E : Territoire SIB, Nom Unique de Projet, Adresse du Projet, Nom Unique d'Immeuble, **Lien vers fiche technique**. Le lien du bloc FICHE TECHNIQUE vient **exclusivement de la colonne E**, copié tel quel. **Jamais le Drive**, ni source ni repli. Immeuble introuvable ou lien manquant : le signaler, sans bloquer le triage.
- **Fiches techniques des immeubles** (~178 fichiers Excel, un par immeuble) : les lire pendant le triage pour calibrer urgence et complexité (chauffage central vs individuel, eau chaude centralisée, intercom). Un « pas d'eau chaude » dans un immeuble à chauffe-eau central = possiblement tout l'immeuble = urgence relevée. **Aucune information d'accès ne se recopie dans la note** — le bloc FICHE TECHNIQUE contient le nom et le lien, rien d'autre. Hors projet : dossier « Fiches techniques (IA) » de Mon Drive de maintenance@; absent = triage sans fiche + signalement en AUTRES NOTES. Ne jamais chercher une fiche ailleurs dans le Drive.
- **Fichier des numéros uniques d'unité** (~4310 unités) : jumeler l'adresse libre du Gravity au numéro officiel. Espace commun = pas de numéro, écrire « espace commun ». Ambiguïté : résolution par le RRIA (section 6) avant de demander.
- **Drive « Immeubles »** : pour les travaux d'envergure (C3-C4, structure, infiltrations), lier le dossier de l'immeuble ou le plan pertinent.
- Le guide du coordonnateur complète cette skill, mais ne prime jamais sur l'agenda.

---

## 11. Étape 5 — Titre, puis note

### Titre — structure intouchable

Format : `[urgence] UNITÉ ADRESSE: Résumé court`

Exemples : `3140-501 France-Prime: Frigo glace congélateur (récidive)` · `AJD 3048-2 Châtelets: Bruit de goutte d'eau dans le mur` · `ajd 125-103 Cèdres: Fourmis partout dans l'appartement`

- **Aucune initiale d'assigné** — ni employé, ni coordonnateur, ni fournisseur. L'assignation n'est pas du ressort du triage (garde-fou 20).
- Items multiples séparés par « / ».
- Les titres **historiques** porteurs d'initiales ne se réécrivent jamais et se décodent comme avant (premières initiales = responsable actuel; suivantes = anciens responsables ou fournisseurs).
- **Trois mentions de triage seulement** sont admises dans un titre :
  1. `[EN TRAITEMENT]` — **transitoire**, préfixe de verrou (section 3), obligatoirement retiré à la libération. Ne survit jamais à un triage terminé.
  2. `DOUBLON POTENTIEL` (majuscules), directement après le numéro d'unité et le deux-points, quand un doublon est soupçonné (section 8).
  3. « Demande de clarification de l'adresse pour Triage », à la suite du titre d'origine d'un appel non triable (section 13.1).

  Aucune autre annotation de triage — pas de délégable, pas de C1, pas de N5.

### Note — format v10.6

La note s'ajoute **au-dessus** de la description existante. Google Calendar accepte le HTML : envoyer de **vraies balises** `<b>`, `<u>`, `<br>`, `<i>`, non échappées. Si le résultat de l'API montre `&lt;b&gt;`, c'est raté — renvoyer.

**Règles de forme.** Trois sections dans cet ordre. **Zéro émoji.** Pas de deux-points après les titres de section (les libellés de blocs, eux, portent le leur). Pas de ligne séparatrice entre les sections. Pas de numérotation des sections. Le titre « SECTION TERRAIN » **n'apparaît plus** dans la note — la zone terrain demeure comme concept, mais après FOLLOW-UP TERRAIN la note enchaîne directement sur PROBLÈMES. Libellés des blocs terrain **gras + soulignés** (`<b><u>LIBELLÉ</u> :</b>`); libellés de la SECTION COORDOS en gras simple. Une ligne vide entre les blocs. **Trois lignes vides** après PROBLÈMES — ou après PHOTOS APPAREIL s'il est présent — avant PERMISSION D'ENTRÉE. Séparateur sandwich avant SECTION COORDOS : quatre lignes vides, deux grosses lignes doubles, sept lignes vides, puis de nouveau deux grosses lignes doubles.

**1. FOLLOW-UP TERRAIN** (tout en haut) — titre seul, **aucune explication**, suivi d'environ 8 lignes vides : zone de saisie mobile où l'employé écrira son rapport après le call.

**2. Zone terrain** — blocs dans cet ordre :

- **PROBLÈMES** — chaque item de la requête, numéroté, intégrant **toute** l'information (les mots du locataire, aucun détail coupé) : le lecteur ne doit jamais avoir besoin de descendre lire la requête Gravity. Format : chaque item **entièrement en gras**, précédé d'une ligne vide — `<b><br>N. [énoncé complet].</b><br>`. **Aucune piste de solution, aucune suggestion, aucun diagnostic.** **Terrain pur** : aucune mécanique de coordination (transfert à un sous-traitant, routage, escalade) — ça vit en SECTION COORDOS. **Épuré** : ni remerciement, ni commentaire de satisfaction, ni mention de photo jointe — ça vit en HISTORIQUE ou AUTRES NOTES. **Trié par urgence** : items réordonnés du plus urgent au moins urgent, l'eau et les dégâts d'eau **toujours** en tête, sécurité ensuite, puis confort, puis esthétique — seul l'ordre change, chaque item garde son contenu intégral. C'est la section la plus critique du call.
- **PHOTOS APPAREIL** — bloc **conditionnel**, présent uniquement quand le call concerne un appareil ou un équipement technique (gym, laveuse, sécheuse, cuisinière, réfrigérateur, micro-ondes, lave-vaisselle, climatisation, thermopompe, fournaise, machine, tout appareil). Placé immédiatement après PROBLÈMES. Libellé standard, copié tel quel : « Prendre des photos générales de l'appareil ainsi que du numéro de modèle et du numéro de série (plaque signalétique), et les transmettre sans faute à la maintenance ou directement au sous-traitant. » Pour un call coordonné avec un sous-traitant, le lecteur visé est le coordonnateur qui coordonne. Call sans appareil = aucun bloc, aucune mention.
- **PERMISSION D'ENTRÉE** — code sec, sans commentaire, parmi les quatre : « Autorisé en tout temps sans restriction » / « Présence du locataire exigée » / « Logement vacant — accès libre » / « Espace commun — aucune coordination locataire requise ». **Ignorer à jamais la mention « (traitement prioritaire) » du formulaire Gravity.**
- **ANIMAUX** — valeur Gravity, croisée au bail. Tout écart se signale en AUTRES NOTES, pas ici.
- **OCCUPANTS** — les **personnes** seulement, un occupant par ligne, format « Nom — tél — courriel », un seul `<br>` entre chaque. Jamais de « · » ni d'empilement. Langue mentionnée seulement si anglais. Aucun occupant au rent roll = « LOGEMENT VACANT — accès libre » en toutes lettres (le bloc BAIL est alors omis). **Toujours issu d'une lecture RRIA réelle — tous les co-titulaires, pas seulement le réquérant Gravity.**
- **BAIL** — le **logement** sur une seule ligne dense : « grandeur — début : date — fin : date », suivi de « (emménagement récent) » si le bail a moins de 3 mois. Début manquant : « début inconnu ». Même lecture RRIA que OCCUPANTS.
- **FICHE TECHNIQUE** — nom de la fiche + lien cliquable de la colonne E de la Table Fondamentale, copié tel quel. **Rien d'autre.**
- **HISTORIQUE** — pour une unité de logement, **tout l'historique des 6 derniers mois**, gris inclus, un appel par ligne, un seul `<br>` entre chaque, ordre **antéchronologique**, format « TITRE (corps verbatim, sans préfixe d'initiales) — date, réglé/actif ». **Seuls les 3 plus récents portent un lien.** Liste **fusionnée** sur les deux agendas, jamais deux listes. **Aucune initiale nulle part.** Espace commun sans historique : « Aucun appel pour cet espace commun dans les 6 derniers mois. »

**3. SECTION COORDOS** — 14 catégories dans cet ordre exact, une par ligne :

1. **TRI** — items + verdicts, très court, quelques mots par item. Verdicts **secs, aucune parenthèse explicative**.
2. **DÉLÉGABLE** — OUI/NON + quoi, très court.
3. **REPORT** — très court; pour le tout-venant : « À la discrétion du superviseur ».
4. **DOUBLONS** — « Aucun » sec s'il n'y en a pas. Sinon : raison en quelques mots + lien cliquable (+ marqueur d'agenda si l'original vit ailleurs). **Jamais de description des recherches, jamais de parenthèse méthodologique.**
5. **CALLS ACTIFS / SYNERGIE** — inventaire exhaustif **dans la filière** (section 8). Format à deux niveaux : **maximum 5 entrées avec lien** `<a href="[htmlLink]">TITRE sans préfixe d'initiales</a> — date`, priorité (1) demandes sœurs du même triage, (2) même corps de métier, (3) proximité de date **sauf samedi**; toutes les autres en compact `TITRE — date` **sans lien**. Un call par ligne, **un seul `<br>` entre chaque, jamais de « · »**. Aucune initiale nulle part. Aucun après exclusions : « Aucun » sec. Pas de formule creuse du genre « greffer au prochain passage » — nommer le call et la date.
6. **UNITÉ** — numéro unique officiel.
7. **PROJET** — nom unique de projet.
8. **TEMPS** — `<30 min` / `30 min-1h` / `1h-2h` / `demi-journée` / `journée+` / `soumission requise`.
9. **COMPLEXITÉ** — format sec `C2 — ouvrier`.
10. **SOUS-TRAITANT** — `Non — interne` / `Oui — [nom/métier]`.
11. **ASSIGNATION PROPOSÉE** — **toujours vide**. Ce champ appartient au coordonnateur, pas au triage. Ne jamais y inscrire d'initiales, même « à titre de suggestion ». Voir garde-fou 20.
12. **ENTENTE LOCATAIRE POUR REPORT OU AUTRE** — **le titre seul**, sans description, sans placeholder, sans ligne à trous. Le coordonnateur y inscrit l'entente après son appel.
13. **AUTRES NOTES** — signalements factuels sans catégorie dédiée, un par ligne : écart animaux déclarés vs bail, réquérant absent du rent roll, électro n'appartenant pas à SIB, photos jointes au courriel, unité résolue par RRIA, fin de bail proche.
14. **EMBOURBEMENT** — dernière ligne, format sec `N5 — critique`.

Puis **signature `BÉLANGER + date`**, puis `----------------------------------------`, puis la **requête Gravity Forms intacte**.

### Gabarit HTML

```html
<b><u>FOLLOW-UP TERRAIN</u></b><br><br><br><br><br><br><br><br><br><b><u>PROBLÈMES :</u></b><br><br><b><br>1. [Énoncé complet du problème — toute l'information de la requête, rien de coupé].</b><br><b><br>2. [Énoncé complet du problème suivant].</b><br>[SI LE CALL CONCERNE UN APPAREIL, insérer ici, sinon omettre : <br><b><u>PHOTOS APPAREIL</u> :</b> Prendre des photos générales de l'appareil ainsi que du numéro de modèle et du numéro de série (plaque signalétique), et les transmettre sans faute à la maintenance ou directement au sous-traitant.]<br><br><br><b><u>PERMISSION D'ENTRÉE</u> :</b> [code sec]<br><br><b><u>ANIMAUX</u> :</b> [valeur Gravity, croisée au bail]<br><br><b><u>OCCUPANTS</u> :</b><br>[Nom occupant 1 — tél — courriel]<br>[Nom occupant 2 — tél — courriel]<br><br><b><u>BAIL</u> :</b> [grandeur — début : date — fin : date] [(emménagement récent) si bail < 3 mois]<br><br><b><u>FICHE TECHNIQUE</u> :</b> <a href="[lien colonne E de la Table Fondamentale]">[nom de la fiche]</a><br><br><b><u>HISTORIQUE</u> :</b><br><a href="[htmlLink]">[APPEL 1 — le plus récent]</a> — [date, réglé/actif]<br><a href="[htmlLink]">[APPEL 2]</a> — [date, réglé/actif]<br><a href="[htmlLink]">[APPEL 3]</a> — [date, réglé/actif]<br>[APPEL 4 sans lien — date, réglé/actif]<br>[… tout le 6 mois de l unité, sans lien]<br><br><br><br><br><b>================================================</b><br><b>================================================</b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><br><b><br></b><b>================================================</b><br><b>================================================</b><br><br><b><u>SECTION COORDOS</u></b><br><br><b>TRI :</b> [item 1 → verdict · item 2 → verdict]<br><br><b>DÉLÉGABLE :</b> [OUI/NON — quoi]<br><br><b>REPORT :</b> [À la discrétion du superviseur / verdict très court]<br><br><b>DOUBLONS :</b> Aucun<br><br><b>CALLS ACTIFS / SYNERGIE :</b><br><a href="[htmlLink copié tel quel]">[TITRE DU CALL 1 verbatim SANS préfixe d'initiales]</a> — [date lue dans l'événement, précision de regroupement]<br><a href="[htmlLink copié tel quel]">[TITRE DU CALL 2 verbatim SANS préfixe d'initiales]</a> — [date]<br>[CALL COMPACT sans initiales ni lien — date]<br><br><b>UNITÉ :</b> [numéro unique officiel]<br><br><b>PROJET :</b> [nom unique de projet]<br><br><b>TEMPS :</b> [tranche standard]<br><br><b>COMPLEXITÉ :</b> [C1-C4 — libellé]<br><br><b>SOUS-TRAITANT :</b> [Non — interne / Oui — nom/métier]<br><br><b>ASSIGNATION PROPOSÉE :</b><br><br><b>ENTENTE LOCATAIRE POUR REPORT OU AUTRE :</b><br><br><b>AUTRES NOTES :</b><br>[signalement factuel bref]<br><br><b>EMBOURBEMENT :</b> N5 — critique<br><br>BÉLANGER [date]<br><br>----------------------------------------<br>[requête Gravity Forms originale intacte]
```

### Ce qui ne se produit plus jamais

Le titre visible « SECTION TERRAIN ». Les paragraphes Analyse / Historique long / Piste de solution. Le libellé « QUOI FAIRE » (renommé PROBLÈMES). L'ancienne section « HISTORIQUE DE L'UNITÉ » du bas. Les émojis. Les initiales dans un titre écrit au triage. Le « Aucune photo (vérifié) ». Les libellés d'entente à trous. Un `[EN TRAITEMENT]` laissé dans un titre après triage. **Des initiales dans ASSIGNATION PROPOSÉE.**

---

## 12. Étape 6 — Contrôles avant `update_event`

Dans cet ordre, à chaque appel, sans exception :

1. **⛔ RELECTURE ANTI-PERTE** — juste avant d'écrire, refaire un `get_event` sur la demande et comparer sa description à celle lue au début du triage. **Si elle a changé, le coordonnateur a écrit pendant le traitement** : intégrer son ajout au-dessus de la requête Gravity, dans la partie existante conservée, au lieu de l'effacer. Ne jamais écrire une description bâtie sur une lecture périmée.
2. **Longueur** — compter la description complète (`len()`). **Budget maximal 7 500 caractères.** Google Calendar tronque silencieusement au-delà d'environ 8 000, **sans erreur ni avertissement** : une note tronquée perd sa requête Gravity, sa signature et ses catégories de queue. En dépassement : réduire les entrées avec lien de la SYNERGIE, puis résumer la queue en « + N autres calls actifs du projet (voir l'agenda) ».
3. **Liens** — chaque lien est un `htmlLink` copié tel quel d'un résultat d'outil de la conversation en cours, visant l'un des deux `calendarId` autorisés (section 5).
4. **Initiales** — aucune initiale d'employé, de coordonnateur ou de fournisseur dans le titre, ni dans SYNERGIE, ni dans HISTORIQUE, **ni dans ASSIGNATION PROPOSÉE**.
5. **Vocabulaire interne** — aucun `A1`-`A5`, « règle cardinale », nom de skill, ni code `C`/`N` hors de ses deux lignes.
6. **Verrou libéré** — le titre final ne contient plus `[EN TRAITEMENT]`.
7. **Balises HTML réelles**, non échappées.
8. **Requête Gravity intacte** en bas, note ajoutée au-dessus.
9. **`notificationLevel: NONE`**, couleur = territoire, **jamais `colorId 8`**, **date inchangée**.
10. **Registre de progression** mis à jour (section 2.3).

---

## 13. Modes particuliers

### 13.1 — Session planifiée (tâche Cowork, coordonnateur absent)

Tout le reste de la skill est identique. Ajustements :

1. **Modèle** : celui fixé à la création de la tâche vaut autorisation permanente — ne jamais bloquer. Mentionner en une ligne au résumé s'il n'est pas Sonnet.
2. **Sources hors projet** : `/mnt/project/` inaccessible → Table Fondamentale et guide dans `references/` de la skill; fiches techniques dans « Fiches techniques (IA) » de Mon Drive de maintenance@, sinon triage sans fiche + signalement. RRIA, tableau vivant et agenda : inchangés.
3. **Triage autonome, couleur appliquée** : titre, note v10.6 **et couleur du territoire** appliqués directement, exactement comme en session normale. La demande ne reste pas verte. La « phase proposition » est abrogée — si un ancien prompt de tâche la déclare encore, cette déclaration est caduque. Le gris demeure strictement interdit.
4. **Ambiguïtés — signaler au lieu de bloquer.** Toute règle « demander au coordonnateur, jamais deviner » se transpose ainsi :
   - **Unité ambiguë ou introuvable** : tenter d'abord la résolution par le RRIA (section 6). Si elle échoue, l'appel est **non triable** — et il ne se laisse **jamais silencieusement intact**, car un call intact est visuellement indiscernable d'un call jamais vu. Quatre gestes : **(i)** titre — retirer `[EN TRAITEMENT]`, restaurer le titre d'origine verbatim, et y ajouter à la suite « Demande de clarification de l'adresse pour Triage », séparé par un deux-points; **(ii)** note — ajouter au-dessus de la requête intacte un court paragraphe factuel : ce qui rend l'unité ambiguë, la recherche RRIA tentée et son résultat, la précision demandée; signé `BÉLANGER + date`; **(iii)** couleur — la demande **reste verte**, pas de couleur de territoire, jamais de gris, date inchangée; **(iv)** signalement au résumé d'exécution.
   - **Tout autre point exigeant une décision humaine** (doublon à griser, RRIA périmé, immeuble absent de la Table) : signalement en AUTRES NOTES et au résumé, sans bloquer le reste de la file.
5. **Résumé d'exécution** : la règle « aucun rapport » vise les rapports dans la conversation du coordonnateur. En tâche planifiée, la sortie est un **court** résumé factuel — nombre de vertes trouvées et traitées, liste « UNITÉ ADRESSE — verdict » une ligne chacune, verrous abandonnés récupérés, cas signalés du point 4, **et le nombre restant avec la raison si l'exécution s'est arrêtée avant de vider la file**. Rien de plus. **Aucune demande verte trouvée = aucune sortie, aucun rapport** : la tâche s'arrête en silence.
6. **Périmètre inchangé** : jamais de suppression, de déplacement de date, de gris, de courriel; notifications NONE.

### 13.2 — Entrée par capture d'écran

Une capture peut **déclencher** un triage; elle n'est **jamais** une source pour la note.

**Branche A — call déjà dans l'agenda.** La capture sert uniquement à **identifier** le call (adresse, unité, ASNU, titre visible). Retrouver le vrai événement par `list_events`/`get_event` pour son vrai titre, sa vraie date, son vrai `htmlLink`. Rien de ce qui est visible dans la capture ne se copie dans la note. Puis triage normal, verrou inclus.

**Branche B — courriel ou signalement pas encore dans l'agenda.** C'est une **création manuelle** :
1. Lire dans la ou les captures les mêmes champs qu'une requête Gravity : réquérant, téléphone, adresse/unité, problème complet, permission, animaux, ASNU si visible. Signalement étalé sur plusieurs captures : reconstituer le texte complet avant de continuer — jamais de triage sur une information partielle.
2. `create_event` : titre normalisé, **couleur verte** tant que le triage n'est pas fait, description = la requête reconstituée intacte. **Date toujours le samedi suivant la date du jour** — si aujourd'hui est un samedi, aujourd'hui. Jamais la date du jour d'un jour de semaine, jamais une date passée, **jamais une date lue dans la capture**.
3. Poursuivre le triage complet à partir de ce nouvel événement, par de vrais appels d'outils.
4. Capture coupée, floue ou incomplète = demander au coordonnateur avant de créer quoi que ce soit.

Plusieurs calls distincts dans un même lot de captures : chacun traité séparément, un verrou à la fois.

### 13.3 — Création manuelle hors capture

Toute nouvelle demande créée manuellement (courriel, appel téléphonique, signalement d'employé — toute source hors du pont Gravity Forms) est datée du **samedi suivant la date du jour**. C'est la même zone d'atterrissage que les demandes Gravity : un humain replacera ensuite l'appel dans une vraie journée de travail. Cette règle couvre la **création**; le garde-fou 2 (ne jamais déplacer un call existant) demeure entier — et une date donnée pour une création ne se transfère jamais à un autre événement de la même session.

---

## 14. Ton

Factuel, intelligent, professionnel, toujours. Jamais de langage familier ou dénigrant. Zéro émoji dans les notes. Les ~7 000 événements historiques gardent leurs émojis — ne pas les « corriger ».
