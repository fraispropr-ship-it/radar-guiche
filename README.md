Radar de Guiche

Une carte mobile des avions signalés près de Guiche (43.5128, -1.2028), alimentée par Airplanes.live. Aucun compte ou clé API nécessaire pour cette version.

Mise en ligne sur GitHub

1. Créer un dépôt public nommé radar-guiche sur GitHub.
2. Extraire cette archive et envoyer le contenu du dossier radar-guiche à la racine du dépôt, y compris le dossier caché .github (il contient l’automatisation).
3. Dans Settings → Pages → Build and deployment, choisir Deploy from a branch, branche main, dossier /(root), puis Save.
4. Dans Actions → Actualiser le radar → Run workflow, lancer une première actualisation. L’adresse sera https://VOTRE-PSEUDO.github.io/radar-guiche/.
5. Ouvrir la page sur téléphone et, si souhaité, l’ajouter à l’écran d’accueil.

La page essaie l’API directement. Si le navigateur refuse cette connexion, elle lit data.json, actualisé en principe toutes les 10 minutes par GitHub Actions. Les exécutions planifiées peuvent subir un retard ; l’heure réelle des données est affichée. En cas de panne de l’API, la dernière copie reste en place et son âge est visible. Les dépôts publics inactifs peuvent voir leurs workflows planifiés désactivés après 60 jours : il faut alors les réactiver dans Actions.

Limites

• Le rayon affiché peut être changé entre 10 et 100 km ; la collecte couvre environ 102 km (55 milles nautiques).
• Le point est le centre approximatif de Guiche, pas une adresse privée.
• La trajectoire complète et l’aéroport de départ ou d’arrivée ne sont pas disponibles dans cette réponse ; le lien de chaque avion ouvre sa fiche chez Airplanes.live.
• Les positions dépendent des récepteurs et ne sont pas destinées à la navigation.
• La carte charge Leaflet et OpenStreetMap via Internet. Un compte GitHub gratuit peut exiger un dépôt public pour GitHub Pages.

Développement local

python3 -m http.server 8000 depuis ce dossier, puis ouvrir http://localhost:8000/. Pour actualiser la copie : python3 scripts/fetch.py.
