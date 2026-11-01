# AEMET Public Weather for Home Assistant

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/icon-dark.svg">
  <img src="assets/icon-light.svg" alt="AEMET Public Weather icon" width="80">
</picture>

Custom Home Assistant integration for AEMET's public weather pages. It does not require an AEMET OpenData API key. Configure a municipality, an observation station, or both; an optional Meteoalerta zone adds warning data.

## What it provides

- **Station:** current hourly temperature, humidity, pressure and three-hour pressure tendency, wind and gust speed/direction, and hourly rain; today's extrema and rain total; last seven completed daily summaries.
- **Municipality:** hourly forecast (up to 48 hours), daily forecast (up to seven days), a `weather` entity, and sensors for the next forecast hour and today/tomorrow.
- **Warning zone:** count and links for warning items published in the regional AEMET RSS feed.

The hourly and daily forecasts are for the municipality. They are **not** a forecast calculated for the selected observation station. The current condition shown by the `weather` entity comes from the municipal forecast; current numerical measurements use the station when a fresh reading exists, then the municipal forecast where possible.

Home Assistant labels the municipality device **AEMET Forecast** and the station device **AEMET Observations**. The `weather` entity is called **Current conditions and forecast** because it combines both sources. These names do not change existing entity IDs.

All entities identify their source and time. A missing value stays unavailable; zero is reported only when AEMET supplies zero. Data automatically becomes unavailable when it is too old. Each document is fetched on its own schedule, and a failure in one document does not discard healthy documents.

## Installation

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=oscahie&repository=aemet-weather-data&category=integration)

Click the badge to open this repository in HACS. Add it as an **Integration** custom repository if prompted, install it, and restart Home Assistant. The equivalent manual repository URL is `https://github.com/oscahie/aemet-weather-data`.

[![Add AEMET Public Weather to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=aemet_public)

Then add **AEMET Public Weather** through the badge or **Settings → Devices & services → Add integration**. Enter at least a municipality ID or a station ID. The warning-zone ID is optional.

For manual installation, copy `custom_components/aemet_public` to your Home Assistant `config/custom_components/` directory, restart Home Assistant, and add the integration through the UI.

Example for Pamplona:

| Setting | Value | Meaning |
| --- | --- | --- |
| Municipality ID | `31201` | Pamplona/Iruña municipal forecast |
| Station ID | `9263D` | Pamplona Aeropuerto observations |
| Warning zone | `743102` | Centro de Navarra |
| Time zone | `Europe/Madrid` | Local dates and forecast hours |

Other valid IDs can be found in the corresponding AEMET page URL. The station and municipality do not need to be the same location. You can add multiple entries and reconfigure each entry later. Changing an existing entry's IDs preserves its Home Assistant entity IDs, so review any automations using them.

## Data sources and refresh

| Source | Public AEMET path | Poll | Maximum age used by entities |
| --- | --- | --- | --- |
| Hourly station observations | `/es/api-eltiempo/udat/tablas-graficas/horario/9/{station}` | 15 min | Last sample and document ≤ 2 h |
| Today's station summary | `/es/api-eltiempo/udat/tablas-graficas/diario/9/{station}/{local_date}T00000` | 15 min | Same local date; document ≤ 2 h |
| Past station daily summaries | `/es/api-eltiempo/udat/tablas-graficas/diario/9/{station}` | 15 min | Document ≤ 48 h; last day ≤ 3 days ago |
| Municipal hourly forecast | `/xml/municipios_h/localidad_h_{municipality}.xml` | 1 h | Fetch ≤ 3 h; issue ≤ 36 h; future hour present |
| Municipal daily forecast | `/xml/municipios/localidad_{municipality}.xml` | 1 h | Fetch ≤ 3 h; issue ≤ 36 h; future day present |
| Meteoalerta RSS | `/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAZ{zone}_RSS.xml` | 30 min | Fetch ≤ 2 h |

The station observation paths are used by AEMET's website, but they are **undocumented internal routes**. Their format has been verified at the time of development, not guaranteed by AEMET. Municipal forecast XML and RSS are public files. The integration logs a source failure once and logs recovery. AEMET may change any format or availability without notice.

Hourly precipitation is a depth for that hour and is **not** a lifetime total. Today's precipitation is an in-progress daily total. Daily summary precipitation belongs to its stated date. Wind direction is unavailable for calm or unknown direction. The precipitation probability sensor uses the current AEMET interval, not a fabricated hourly probability; its interval start and end are attributes. The count of warning items means **published warnings**, which may include future effective periods; inspect each linked warning for its validity.

## Requirements and attribution

- Home Assistant Core 2026.10 or newer (the version used for development).
- Internet access from Home Assistant to `www.aemet.es` over HTTPS.
- AEMET data attribution is included on entities. Consult [AEMET's legal notice](https://www.aemet.es/es/nota_legal) before redistributing data.

This is a community integration and is not affiliated with AEMET or Home Assistant. Report parsing problems with the affected station/municipality ID and the source type; do not post Home Assistant tokens or private URLs.

## Development

Run the parser regression tests with `python3 -m unittest discover -s tests -v`. The tests include saved public AEMET XML and need no Home Assistant installation or network connection.

## License

MIT. See [LICENSE](LICENSE). The license covers this integration's source code; AEMET retains its own rights to the weather data.
