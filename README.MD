<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
<div align="center">

[![Contributors][contributors-shield]][contributors-url][![Forks][forks-shield]][forks-url][![Stargazers][stars-shield]][stars-url][![Issues][issues-shield]][issues-url][![MIT License][license-shield]][license-url]

</div>

<!-- PROJECT LOGO / HEADER -->
<br />
<div align="center">
  <h1 align="center">⚔️ Super League FPL H2H</h1>

  <p align="center">
    A high-performance Head-to-Head Fantasy Premier League tracker built with FastAPI, Jinja2, and custom persistent disk caching.
    <br />
    <br />
    <a href="https://super-league.onrender.com"><strong>View Live Demo »</strong></a>
    <br />
    <br />
    <a href="#about-the-project">About The Project</a>
    ·
    <a href="#features">Key Features</a>
    ·
    <a href="#getting-started">Getting Started</a>
    ·
    <a href="#license">License</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li><a href="#features">Features</a></li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

**Super League FPL H2H** is a specialized platform created to track and simulate 7v7 Head-to-Head matchups for Fantasy Premier League mini-leagues. It provides transparent differential breakdowns, complete schedules, live & finalized scoreboards, and exact statistical standings without relying on manual spreadsheets.

🌐 **Live Deployment:** [https://super-league.onrender.com](https://super-league.onrender.com)

### Built With

[![Python][Python.org]][Python-url][![FastAPI][FastAPI.tiangolo.com]][FastAPI-url][![Bootstrap][Bootstrap.com]][Bootstrap-url][![Jinja2][Jinja.palletsprojects.com]][Jinja-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- FEATURES -->
## Features

* **⚔️ Squad Differential Comparison (`/compare`):**
  Detailed side-by-side comparison of two squads for any gameweek, displaying chip statuses, transfer hit subtractions, and net positional differentials.
* **📅 Fixtures & Scoreboard (`/fixtures`):**
  Gameweek-by-gameweek fixture viewer with centered scores and instant access to detailed match views.
* **🏆 Official Standings Table (`/standings`):**
  Precise standings table tracking Matches Played (Pl), Wins (W), Draws (D), Losses (L), Total Points (Pts), and official cumulative Goal Difference (GD).
* **🔄 Dynamic Roster Ranges:**
  Support for mid-season team squad changes and manager transfers through historical gameweek ranges (`from_gw`, `to_gw`, `ids`).
* **⚡ Smart Disk Caching:**
  Persistently stores finalized gameweeks to eliminate redundant requests and safeguard against official FPL API rate limits.
* **🌙 JetBrains Dark Theme:**
  Custom UI built with segmented pill navigation and responsive typography.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

Follow these steps to run a local instance of the application.

### Prerequisites

* Python 3.10 or higher
* Git

### Installation

1. Clone the repository:
   ```bash
   git clone [https://github.com/FeriCodes/super-league-fpl.git](https://github.com/FeriCodes/super-league-fpl.git)
   cd super-league-fpl
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install project dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the development server:
   ```bash
   uvicorn app.main:app --reload
   ```

5. Open your browser and navigate to:
   ```text
   [http://127.0.0.1:8000](http://127.0.0.1:8000)
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE -->
## Usage

* **Configuration:** Edit `app/sl_teams.json` to define team rosters and manage historical squad updates across gameweeks.
* **Schedule:** Configure matchups in `app/fixtures.json` to automatically link head-to-head fixtures.
* **Standings:** Standings are computed automatically on the `/standings` page once gameweek results are finalized.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Hossein Bigdeli - [@FeriCodes](https://github.com/FeriCodes)

Project Link: [https://github.com/FeriCodes/super-league-fpl](https://github.com/FeriCodes/super-league-fpl)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[contributors-shield]: https://img.shields.io/github/contributors/FeriCodes/super-league-fpl.svg?style=for-the-badge
[contributors-url]: https://github.com/FeriCodes/super-league-fpl/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/FeriCodes/super-league-fpl.svg?style=for-the-badge
[forks-url]: https://github.com/FeriCodes/super-league-fpl/network/members
[stars-shield]: https://img.shields.io/github/stars/FeriCodes/super-league-fpl.svg?style=for-the-badge
[stars-url]: https://github.com/FeriCodes/super-league-fpl/stargazers
[issues-shield]: https://img.shields.io/github/issues/FeriCodes/super-league-fpl.svg?style=for-the-badge
[issues-url]: https://github.com/FeriCodes/super-league-fpl/issues
[license-shield]: https://img.shields.io/github/license/FeriCodes/super-league-fpl.svg?style=for-the-badge
[license-url]: https://github.com/FeriCodes/super-league-fpl/blob/main/LICENSE
[Python.org]: https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white
[Python-url]: https://www.python.org/
[FastAPI.tiangolo.com]: https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi
[FastAPI-url]: https://fastapi.tiangolo.com/
[Bootstrap.com]: https://img.shields.io/badge/Bootstrap-563D7C?style=for-the-badge&logo=bootstrap&logoColor=white
[Bootstrap-url]: https://getbootstrap.com/
[Jinja.palletsprojects.com]: https://img.shields.io/badge/Jinja2-B41717?style=for-the-badge&logo=jinja&logoColor=white
[Jinja-url]: https://jinja.palletsprojects.com/