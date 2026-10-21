#!/usr/bin/env python3
"""
Desktop Sun & Moon Tracker Widget
GTK3 + Cairo transparent desktop overlay for Ubuntu.
Panoramic sky view: left=East, centre=South, right=West.
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib

import cairo
import math
import json
import os
import datetime
import random
import time
import threading
import glob
import subprocess
import urllib.request

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

DEFAULT_CONFIG = {
    "latitude": 6.1375,
    "longitude": 1.2123,
    "timezone_offset": 0,
    "aster_scale": 1.0,
    "cards": {
        "clock": True,
        "location": True,
        "sunrise_sunset": True,
        "solar_noon": True,
        "moon_phase": True,
        "moon_rise_set": True,
        "daylight_remaining": True,
        "cloud_cover": True
    },
    "clean_mode": False,
    "keep_above": False,
    "sticky": True,
    "show_constellations": True,
    "show_silhouette": True,
    "show_compass": True,
    "show_horizon_labels": True,
    "show_rainbow": True,
    "show_info_cards": False,
    "show_weekly_forecast": True,
    "language": "auto",
    "lockscreen_export": "off",
    "facing": 180.0,
    "compass_port": "",
    "app_enabled": True
}

_NO_CLOUDS = {
    'total': 0, 'low': 0, 'mid': 0, 'high': 0,
    'precip': 0.0, 'snow': False, 'wmo': 0, 'ts': '',
    'temp': None, 'humidity': None,
    'wind_speed': 0.0, 'wind_dir': 0.0,
    'symbol': '', 'forecast': [], 'daily_forecast': [], 'hourly_forecast': [],
}

_FACING = 180.0   # azimuth the panorama is centred on; updated each frame from config

# ─── Weather condition label / accent colour (shared by forecast & weekly) ────
_WX_LABEL = {
    'clearsky': 'Clear', 'fair': 'Fair',
    'partlycloudy': 'Part. Cloudy', 'cloudy': 'Cloudy', 'fog': 'Fog',
    'lightrain': 'Light Rain', 'rain': 'Rain', 'heavyrain': 'Heavy Rain',
    'lightsleet': 'Sleet', 'sleet': 'Sleet',
    'lightsnow': 'Light Snow', 'snow': 'Snow', 'heavysnow': 'Heavy Snow',
    'lightrainshowers': 'Showers', 'rainshowers': 'Showers',
    'heavyrainshowers': 'Hvy Showers', 'lightsnowshowers': 'Snow Shwrs',
    'snowshowers': 'Snow Shwrs', 'thunderstorm': 'Thunder',
    'rainandthunder': 'Storm', 'heavyrainandthunder': 'Heavy Storm',
    'lightsleetshowers': 'Sleet Shwrs', 'sleetshowers': 'Sleet Shwrs',
}
_WX_ACCENT = {
    'clearsky': (1.00, 0.92, 0.45), 'fair': (1.00, 0.88, 0.55),
    'partlycloudy': (0.78, 0.88, 1.00), 'cloudy': (0.68, 0.78, 0.95),
    'fog': (0.72, 0.80, 0.85),
    'lightrain': (0.50, 0.82, 1.00), 'rain': (0.38, 0.68, 1.00),
    'heavyrain': (0.28, 0.55, 1.00),
    'lightsleet': (0.70, 0.85, 1.00), 'sleet': (0.65, 0.80, 1.00),
    'lightsnow': (0.82, 0.92, 1.00), 'snow': (0.78, 0.90, 1.00),
    'heavysnow': (0.72, 0.86, 1.00),
    'lightrainshowers': (0.55, 0.80, 1.00), 'rainshowers': (0.45, 0.72, 1.00),
    'heavyrainshowers': (0.35, 0.62, 1.00),
    'thunderstorm': (0.90, 0.62, 1.00), 'rainandthunder': (0.85, 0.50, 1.00),
    'heavyrainandthunder': (0.80, 0.40, 1.00),
}

# ─── i18n ─────────────────────────────────────────────────────────────────────

_LANG = 'en'

_DAYS_SHORT = {
    'en': ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
    'fr': ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'],
    'es': ['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'],
    'de': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'],
    'pt': ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'],
    'it': ['Lun','Mar','Mer','Gio','Ven','Sab','Dom'],
}
_MONTHS_SHORT = {
    'en': ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    'fr': ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc'],
    'es': ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'],
    'de': ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'],
    'pt': ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'],
    'it': ['Gen','Feb','Mar','Apr','Mag','Giu','Lug','Ago','Set','Ott','Nov','Dic'],
}

_TRANSLATIONS = {
    'en': {
        'pct_elapsed': '{pct}% of day elapsed',
        'sunrise_in':  'Sunrise in {h}h {m:02d}m',
    },
    'fr': {
        'LOCAL TIME': 'HEURE LOCALE',       'LOCATION': 'LOCALISATION',
        'SUNRISE / SUNSET': 'LEVER / COUCHER', 'SOLAR NOON': 'MIDI SOLAIRE',
        'MOON PHASE': 'PHASE LUNAIRE',      'MOONRISE / MOONSET': 'LEVER / COUCHER LUNE',
        'DAYLIGHT LEFT': 'DURÉE RESTANTE',  'CLOUD COVER': 'COUVERTURE NUAGEUSE',
        'New Moon': 'Nouvelle Lune',        'Waxing Crescent': 'Croissant',
        'First Quarter': 'Premier Quartier','Waxing Gibbous': 'Gibbeuse Croiss.',
        'Full Moon': 'Pleine Lune',         'Waning Gibbous': 'Gibbeuse Décr.',
        'Last Quarter': 'Dernier Quartier', 'Waning Crescent': 'Décroissant',
        'Clear': 'Dégagé',    'Fair': 'Beau',     'Part. Cloudy': 'Peu Nuageux',
        'Cloudy': 'Nuageux',  'Fog': 'Brouillard','Light Rain': 'Pluie Légère',
        'Rain': 'Pluie',      'Heavy Rain': 'Forte Pluie',
        'Sleet': 'Grésil',    'Light Snow': 'Neige Légère',
        'Snow': 'Neige',      'Heavy Snow': 'Forte Neige',
        'Showers': 'Averses', 'Hvy Showers': 'F. Averses',
        'Snow Shwrs': 'Av. Neigeux', 'Sleet Shwrs': 'Av. Grésil',
        'Thunder': 'Orage',   'Storm': 'Tempête',  'Heavy Storm': 'Forte Tempête',
        'Night': 'Nuit',      'Today': "Aujourd'hui",
        'pct_elapsed': '{pct}% du jour écoulé',
        'sunrise_in':  'Lever dans {h}h {m:02d}m',
        'Sky Overlay Active': 'Overlay Actif',
        'Start with GNOME session': 'Démarrer avec GNOME',
        'Aster Size': 'Taille des Astres',
        'Astronomical Info Cards': 'Infos Astronomiques',
        'Visible Cards': 'Cartes Visibles',
        'Clock & Date': 'Horloge & Date',
        'Location & Coordinates': 'Lieu & Coordonnées',
        'Sunrise & Sunset': 'Lever & Coucher',
        'Solar Noon & Elevation': 'Midi & Élévation',
        'Moon Phase & Age': 'Phase & Âge Lunaire',
        'Moon Rise & Set': 'Lever & Coucher Lune',
        'Daylight Remaining': 'Durée Restante',
        'Cloud Cover': 'Couverture Nuageuse',
        'Clean Mode  (Ctrl+H)': 'Mode Épuré (Ctrl+H)',
        'Constellation Lines': 'Constellations',
        'Horizon Silhouette': 'Silhouette Horizon',
        'Compass Rose': 'Rose des Vents',
        'Horizon Direction Labels': 'Étiquettes Horizon',
        'Rainbow': 'Arc-en-ciel',
        'Weekly Forecast Column': 'Prévisions Semaine',
        'Export sky as wallpaper': "Fond d'écran",
        'Disabled': 'Désactivé',
        'Desktop background only': 'Fond de bureau',
        'Lock screen only': 'Écran verrouillage',
        'Both background & lock screen': 'Les deux',
        'Language': 'Langue',
        'Screen facing direction': "Direction de l'écran",
        'External serial compass port': 'Port compas externe',
        'Connect': 'Connecter',
        'Location': 'Localisation',
        'Detect automatically': 'Détection auto.',
        'Latitude  (+N / -S)': 'Latitude (+N / -S)',
        'Longitude (+E / -W)': 'Longitude (+E / -O)',
        'Timezone': 'Fuseau horaire',
        'Save & Apply': 'Enregistrer',
        'Facing North': 'Face au Nord',           'Facing North-East': 'Face au Nord-Est',
        'Facing East': "Face à l'Est",            'Facing South-East': 'Face au Sud-Est',
        'Facing South (default)': 'Face au Sud (défaut)',
        'Facing South-West': 'Face au Sud-Ouest', 'Facing West': "Face à l'Ouest",
        'Facing North-West': 'Face au Nord-Ouest',
    },
    'es': {
        'LOCAL TIME': 'HORA LOCAL',         'LOCATION': 'UBICACIÓN',
        'SUNRISE / SUNSET': 'AMANECER / ATARDECER', 'SOLAR NOON': 'MEDIODÍA SOLAR',
        'MOON PHASE': 'FASE LUNAR',         'MOONRISE / MOONSET': 'SALIDA / PUESTA LUNA',
        'DAYLIGHT LEFT': 'LUZ RESTANTE',    'CLOUD COVER': 'NUBOSIDAD',
        'New Moon': 'Luna Nueva',           'Waxing Crescent': 'Creciente',
        'First Quarter': 'Cuarto Creciente','Waxing Gibbous': 'Gibosa Creciente',
        'Full Moon': 'Luna Llena',          'Waning Gibbous': 'Gibosa Menguante',
        'Last Quarter': 'Cuarto Menguante', 'Waning Crescent': 'Menguante',
        'Clear': 'Despejado', 'Fair': 'Bueno',   'Part. Cloudy': 'Poco Nuboso',
        'Cloudy': 'Nublado',  'Fog': 'Niebla',   'Light Rain': 'Lluvia Leve',
        'Rain': 'Lluvia',     'Heavy Rain': 'Lluvia Intensa',
        'Sleet': 'Aguanieve', 'Light Snow': 'Nieve Leve',
        'Snow': 'Nieve',      'Heavy Snow': 'Nevada Intensa',
        'Showers': 'Chubascos','Hvy Showers': 'Chub. Fuertes',
        'Snow Shwrs': 'Chub. Nieve', 'Sleet Shwrs': 'Chub. Granizo',
        'Thunder': 'Tormenta','Storm': 'Tempestad','Heavy Storm': 'Gran Tormenta',
        'Night': 'Noche',     'Today': 'Hoy',
        'pct_elapsed': '{pct}% del día',
        'sunrise_in':  'Amanecer en {h}h {m:02d}m',
        'Sky Overlay Active': 'Overlay Activo',
        'Start with GNOME session': 'Iniciar con GNOME',
        'Aster Size': 'Tamaño de Astros',
        'Astronomical Info Cards': 'Info Astronómica',
        'Visible Cards': 'Tarjetas Visibles',
        'Clock & Date': 'Reloj & Fecha',
        'Location & Coordinates': 'Lugar & Coords',
        'Sunrise & Sunset': 'Amanecer & Atardecer',
        'Solar Noon & Elevation': 'Mediodía & Elevación',
        'Moon Phase & Age': 'Fase & Edad Lunar',
        'Moon Rise & Set': 'Salida & Puesta Luna',
        'Daylight Remaining': 'Luz Restante',
        'Cloud Cover': 'Nubosidad',
        'Clean Mode  (Ctrl+H)': 'Modo Limpio (Ctrl+H)',
        'Constellation Lines': 'Constelaciones',
        'Horizon Silhouette': 'Silueta Horizonte',
        'Compass Rose': 'Rosa de los Vientos',
        'Horizon Direction Labels': 'Etiquetas Horizonte',
        'Rainbow': 'Arcoíris',
        'Weekly Forecast Column': 'Pronóstico Semanal',
        'Export sky as wallpaper': 'Fondo de pantalla',
        'Disabled': 'Desactivado',
        'Desktop background only': 'Fondo de escritorio',
        'Lock screen only': 'Pantalla de bloqueo',
        'Both background & lock screen': 'Ambos',
        'Language': 'Idioma',
        'Screen facing direction': 'Dirección pantalla',
        'External serial compass port': 'Puerto brújula ext.',
        'Connect': 'Conectar',
        'Location': 'Ubicación',
        'Detect automatically': 'Detección automática',
        'Latitude  (+N / -S)': 'Latitud (+N / -S)',
        'Longitude (+E / -W)': 'Longitud (+E / -O)',
        'Timezone': 'Zona horaria',
        'Save & Apply': 'Guardar',
        'Facing North': 'Mirando al Norte',       'Facing North-East': 'Mirando al Noreste',
        'Facing East': 'Mirando al Este',         'Facing South-East': 'Mirando al Sureste',
        'Facing South (default)': 'Mirando al Sur (default)',
        'Facing South-West': 'Mirando al Suroeste','Facing West': 'Mirando al Oeste',
        'Facing North-West': 'Mirando al Noroeste',
    },
    'de': {
        'LOCAL TIME': 'ORTSZEIT',           'LOCATION': 'STANDORT',
        'SUNRISE / SUNSET': 'AUFGANG / UNTERGANG', 'SOLAR NOON': 'SONNENMITTAG',
        'MOON PHASE': 'MONDPHASE',          'MOONRISE / MOONSET': 'MONDAUF- / -UNTERGANG',
        'DAYLIGHT LEFT': 'TAGESLICHT REST', 'CLOUD COVER': 'BEWÖLKUNG',
        'New Moon': 'Neumond',              'Waxing Crescent': 'Zunehmend',
        'First Quarter': 'Erstes Viertel',  'Waxing Gibbous': 'Zunehm. Oval',
        'Full Moon': 'Vollmond',            'Waning Gibbous': 'Abnehm. Oval',
        'Last Quarter': 'Letztes Viertel',  'Waning Crescent': 'Abnehmend',
        'Clear': 'Klar',       'Fair': 'Schön',    'Part. Cloudy': 'Teils Bewölkt',
        'Cloudy': 'Bewölkt',   'Fog': 'Nebel',     'Light Rain': 'Leichter Regen',
        'Rain': 'Regen',       'Heavy Rain': 'Starkregen',
        'Sleet': 'Schneeregen','Light Snow': 'Leichter Schnee',
        'Snow': 'Schnee',      'Heavy Snow': 'Starker Schnee',
        'Showers': 'Schauer',  'Hvy Showers': 'Starke Schauer',
        'Snow Shwrs': 'Schneeschauer','Sleet Shwrs': 'Schneeregenscha.',
        'Thunder': 'Gewitter', 'Storm': 'Sturm',   'Heavy Storm': 'Schwerer Sturm',
        'Night': 'Nacht',      'Today': 'Heute',
        'pct_elapsed': '{pct}% des Tages',
        'sunrise_in':  'Sonnenaufgang in {h}h {m:02d}m',
        'Sky Overlay Active': 'Overlay Aktiv',
        'Start with GNOME session': 'Mit GNOME starten',
        'Aster Size': 'Gestirngröße',
        'Astronomical Info Cards': 'Astro-Infokarten',
        'Visible Cards': 'Sichtbare Karten',
        'Clock & Date': 'Uhr & Datum',
        'Location & Coordinates': 'Ort & Koordinaten',
        'Sunrise & Sunset': 'Auf- & Untergang',
        'Solar Noon & Elevation': 'Mittag & Elevation',
        'Moon Phase & Age': 'Mondphase & Alter',
        'Moon Rise & Set': 'Mondauf- & -untergang',
        'Daylight Remaining': 'Tageslicht Rest',
        'Cloud Cover': 'Bewölkung',
        'Clean Mode  (Ctrl+H)': 'Saubermodus (Ctrl+H)',
        'Constellation Lines': 'Sternbilder',
        'Horizon Silhouette': 'Horizontsilhouette',
        'Compass Rose': 'Kompassrose',
        'Horizon Direction Labels': 'Himmelsrichtungen',
        'Rainbow': 'Regenbogen',
        'Weekly Forecast Column': 'Wochenvorhersage',
        'Export sky as wallpaper': 'Als Hintergrundbild',
        'Disabled': 'Deaktiviert',
        'Desktop background only': 'Nur Hintergrundbild',
        'Lock screen only': 'Nur Sperrbildschirm',
        'Both background & lock screen': 'Beides',
        'Language': 'Sprache',
        'Screen facing direction': 'Bildschirmausrichtung',
        'External serial compass port': 'Externer Serienkompass',
        'Connect': 'Verbinden',
        'Location': 'Standort',
        'Detect automatically': 'Automatisch erkennen',
        'Latitude  (+N / -S)': 'Breitengrad (+N / -S)',
        'Longitude (+E / -W)': 'Längengrad (+O / -W)',
        'Timezone': 'Zeitzone',
        'Save & Apply': 'Speichern',
        'Facing North': 'Richtung Nord',          'Facing North-East': 'Richtung Nordost',
        'Facing East': 'Richtung Ost',            'Facing South-East': 'Richtung Südost',
        'Facing South (default)': 'Richtung Süd (Standard)',
        'Facing South-West': 'Richtung Südwest',  'Facing West': 'Richtung West',
        'Facing North-West': 'Richtung Nordwest',
    },
    'pt': {
        'LOCAL TIME': 'HORA LOCAL',         'LOCATION': 'LOCALIZAÇÃO',
        'SUNRISE / SUNSET': 'NASCER / PÔR DO SOL', 'SOLAR NOON': 'MEIO-DIA SOLAR',
        'MOON PHASE': 'FASE LUNAR',         'MOONRISE / MOONSET': 'NASCER / PÔR DA LUA',
        'DAYLIGHT LEFT': 'LUZ RESTANTE',    'CLOUD COVER': 'COBERTURA NUV.',
        'New Moon': 'Lua Nova',             'Waxing Crescent': 'Crescente',
        'First Quarter': 'Quarto Crescente','Waxing Gibbous': 'Gibosa Crescente',
        'Full Moon': 'Lua Cheia',           'Waning Gibbous': 'Gibosa Minguante',
        'Last Quarter': 'Quarto Minguante', 'Waning Crescent': 'Minguante',
        'Clear': 'Limpo',    'Fair': 'Bom',       'Part. Cloudy': 'Pouco Nublado',
        'Cloudy': 'Nublado', 'Fog': 'Névoa',      'Light Rain': 'Chuva Fraca',
        'Rain': 'Chuva',     'Heavy Rain': 'Chuva Forte',
        'Sleet': 'Granizo',  'Light Snow': 'Neve Fraca',
        'Snow': 'Neve',      'Heavy Snow': 'Neve Forte',
        'Showers': 'Aguaceiros','Hvy Showers': 'Aguaceiros Fortes',
        'Snow Shwrs': 'Aguac. Neve','Sleet Shwrs': 'Aguac. Granizo',
        'Thunder': 'Trovoada','Storm': 'Tempestade','Heavy Storm': 'Tempestade Forte',
        'Night': 'Noite',    'Today': 'Hoje',
        'pct_elapsed': '{pct}% do dia',
        'sunrise_in':  'Nascer em {h}h {m:02d}m',
        'Sky Overlay Active': 'Overlay Ativo',
        'Start with GNOME session': 'Iniciar com GNOME',
        'Aster Size': 'Tamanho dos Astros',
        'Astronomical Info Cards': 'Info Astronómica',
        'Visible Cards': 'Cartões Visíveis',
        'Clock & Date': 'Relógio & Data',
        'Location & Coordinates': 'Local & Coordenadas',
        'Sunrise & Sunset': 'Nascer & Pôr do Sol',
        'Solar Noon & Elevation': 'Meio-Dia & Elevação',
        'Moon Phase & Age': 'Fase & Idade Lunar',
        'Moon Rise & Set': 'Nascer & Pôr da Lua',
        'Daylight Remaining': 'Luz Restante',
        'Cloud Cover': 'Cobertura Nuv.',
        'Clean Mode  (Ctrl+H)': 'Modo Limpo (Ctrl+H)',
        'Constellation Lines': 'Constelações',
        'Horizon Silhouette': 'Silhueta Horizonte',
        'Compass Rose': 'Rosa dos Ventos',
        'Horizon Direction Labels': 'Etiquetas Horizonte',
        'Rainbow': 'Arco-íris',
        'Weekly Forecast Column': 'Previsão Semanal',
        'Export sky as wallpaper': 'Fundo de ecrã',
        'Disabled': 'Desativado',
        'Desktop background only': 'Fundo de ambiente',
        'Lock screen only': 'Ecrã de bloqueio',
        'Both background & lock screen': 'Ambos',
        'Language': 'Idioma',
        'Screen facing direction': 'Direção do ecrã',
        'External serial compass port': 'Porta bússola ext.',
        'Connect': 'Ligar',
        'Location': 'Localização',
        'Detect automatically': 'Deteção automática',
        'Latitude  (+N / -S)': 'Latitude (+N / -S)',
        'Longitude (+E / -W)': 'Longitude (+E / -O)',
        'Timezone': 'Fuso horário',
        'Save & Apply': 'Guardar',
        'Facing North': 'Virado a Norte',         'Facing North-East': 'Virado a Nordeste',
        'Facing East': 'Virado a Este',           'Facing South-East': 'Virado a Sudeste',
        'Facing South (default)': 'Virado a Sul (padrão)',
        'Facing South-West': 'Virado a Sudoeste', 'Facing West': 'Virado a Oeste',
        'Facing North-West': 'Virado a Noroeste',
    },
    'it': {
        'LOCAL TIME': 'ORA LOCALE',         'LOCATION': 'POSIZIONE',
        'SUNRISE / SUNSET': 'ALBA / TRAMONTO', 'SOLAR NOON': 'MEZZOGIORNO SOL.',
        'MOON PHASE': 'FASE LUNARE',        'MOONRISE / MOONSET': 'SORGERE / TRAMONTO LUNA',
        'DAYLIGHT LEFT': 'LUCE RESTANTE',   'CLOUD COVER': 'COPERTURA NUVOLOSA',
        'New Moon': 'Luna Nuova',           'Waxing Crescent': 'Crescente',
        'First Quarter': 'Primo Quarto',    'Waxing Gibbous': 'Gibbosa Crescente',
        'Full Moon': 'Luna Piena',          'Waning Gibbous': 'Gibbosa Calante',
        'Last Quarter': 'Ultimo Quarto',    'Waning Crescent': 'Calante',
        'Clear': 'Sereno',  'Fair': 'Bello',     'Part. Cloudy': 'Poco Nuvoloso',
        'Cloudy': 'Nuvoloso','Fog': 'Nebbia',    'Light Rain': 'Pioggia Leggera',
        'Rain': 'Pioggia',  'Heavy Rain': 'Pioggia Forte',
        'Sleet': 'Nevischio','Light Snow': 'Neve Leggera',
        'Snow': 'Neve',     'Heavy Snow': 'Neve Forte',
        'Showers': 'Rovesci','Hvy Showers': 'Rovesci Forti',
        'Snow Shwrs': 'Nevicate','Sleet Shwrs': 'Nevischio',
        'Thunder': 'Temporale','Storm': 'Tempesta','Heavy Storm': 'Tempesta Forte',
        'Night': 'Notte',   'Today': 'Oggi',
        'pct_elapsed': '{pct}% del giorno',
        'sunrise_in':  'Alba in {h}h {m:02d}m',
        'Sky Overlay Active': 'Overlay Attivo',
        'Start with GNOME session': 'Avvia con GNOME',
        'Aster Size': 'Dimensione Astri',
        'Astronomical Info Cards': 'Info Astronomiche',
        'Visible Cards': 'Schede Visibili',
        'Clock & Date': 'Orologio & Data',
        'Location & Coordinates': 'Luogo & Coordinate',
        'Sunrise & Sunset': 'Alba & Tramonto',
        'Solar Noon & Elevation': 'Mezzogiorno & Elev.',
        'Moon Phase & Age': 'Fase & Età Lunare',
        'Moon Rise & Set': 'Sorgere & Tramonto Luna',
        'Daylight Remaining': 'Luce Restante',
        'Cloud Cover': 'Copertura Nuvolosa',
        'Clean Mode  (Ctrl+H)': 'Modalità Pulita (Ctrl+H)',
        'Constellation Lines': 'Costellazioni',
        'Horizon Silhouette': 'Silhouette Orizzonte',
        'Compass Rose': 'Rosa dei Venti',
        'Horizon Direction Labels': 'Etichette Orizzonte',
        'Rainbow': 'Arcobaleno',
        'Weekly Forecast Column': 'Previsioni Settimanali',
        'Export sky as wallpaper': 'Sfondo desktop',
        'Disabled': 'Disattivato',
        'Desktop background only': 'Solo sfondo',
        'Lock screen only': 'Solo schermata blocco',
        'Both background & lock screen': 'Entrambi',
        'Language': 'Lingua',
        'Screen facing direction': 'Direzione schermo',
        'External serial compass port': 'Porta bussola seriale',
        'Connect': 'Connetti',
        'Location': 'Posizione',
        'Detect automatically': 'Rileva automaticamente',
        'Latitude  (+N / -S)': 'Latitudine (+N / -S)',
        'Longitude (+E / -W)': 'Longitudine (+E / -O)',
        'Timezone': 'Fuso orario',
        'Save & Apply': 'Salva',
        'Facing North': 'Rivolto a Nord',         'Facing North-East': 'Rivolto a Nord-Est',
        'Facing East': 'Rivolto a Est',           'Facing South-East': 'Rivolto a Sud-Est',
        'Facing South (default)': 'Rivolto a Sud (predefinito)',
        'Facing South-West': 'Rivolto a Sud-Ovest','Facing West': 'Rivolto a Ovest',
        'Facing North-West': 'Rivolto a Nord-Ovest',
    },
}

_LANG_OPTIONS = [
    ('auto', 'System default'),
    ('en',   'English'),
    ('fr',   'Français'),
    ('es',   'Español'),
    ('de',   'Deutsch'),
    ('pt',   'Português'),
    ('it',   'Italiano'),
]

def _detect_system_lang():
    try:
        import locale as _lc
        code = (_lc.getdefaultlocale()[0] or 'en').split('_')[0].lower()
        if code in _TRANSLATIONS:
            return code
    except Exception:
        pass
    return 'en'

def _set_lang(setting):
    global _LANG
    valid = set(_TRANSLATIONS.keys()) | {'en'}
    _LANG = (setting if setting in valid else _detect_system_lang()) if setting != 'auto' else _detect_system_lang()

def _t(key):
    """Translate key; falls back to 'en' dict for parametric strings, then to key itself."""
    v = _TRANSLATIONS.get(_LANG, {}).get(key)
    if v is not None:
        return v
    v = _TRANSLATIONS.get('en', {}).get(key)
    return v if v is not None else key

def _day_name(weekday_0):
    return (_DAYS_SHORT.get(_LANG) or _DAYS_SHORT['en'])[weekday_0]

def _month_name(month_1):
    return (_MONTHS_SHORT.get(_LANG) or _MONTHS_SHORT['en'])[month_1 - 1]

def _fmt_date(dt):
    return f"{_day_name(dt.weekday())}  {dt.day:02d} {_month_name(dt.month)} {dt.year}"

_PHASE_NAMES = [
    'New Moon', 'Waxing Crescent', 'First Quarter', 'Waxing Gibbous',
    'Full Moon', 'Waning Gibbous', 'Last Quarter', 'Waning Crescent',
]

# ─── Star catalog ─────────────────────────────────────────────────────────────
# (ra_hours, dec_degrees, visual_magnitude, b_v_color_index)
_STARS = [
    # ── mag < 1.5 ──────────────────────────────────────────────────────────
    ( 6.753, -16.716, -1.46,  0.01),  # Sirius         α CMa
    ( 6.399, -52.696, -0.74,  0.16),  # Canopus        α Car
    (14.660, -60.833, -0.27,  0.71),  # Rigil Kent     α Cen
    (14.261,  19.182, -0.05,  1.23),  # Arcturus       α Boo
    (18.616,  38.784,  0.03,  0.00),  # Vega           α Lyr
    ( 5.278,  45.998,  0.08,  0.80),  # Capella        α Aur
    ( 5.242,  -8.202,  0.13, -0.03),  # Rigel          β Ori
    ( 7.655,   5.225,  0.38,  0.42),  # Procyon        α CMi
    ( 1.629, -57.237,  0.46, -0.16),  # Achernar       α Eri
    ( 5.920,   7.407,  0.45,  1.85),  # Betelgeuse     α Ori
    (14.064, -60.373,  0.61, -0.23),  # Hadar          β Cen
    (19.847,   8.868,  0.77,  0.22),  # Altair         α Aql
    (12.443, -63.099,  0.87, -0.24),  # Acrux          α Cru
    ( 4.599,  16.509,  0.87,  1.54),  # Aldebaran      α Tau
    (16.490, -26.432,  0.96,  1.83),  # Antares        α Sco
    (13.420, -11.161,  0.98, -0.24),  # Spica          α Vir
    ( 7.755,  28.026,  1.14,  1.00),  # Pollux         β Gem
    (22.961, -29.622,  1.16,  0.09),  # Fomalhaut      α PsA
    (20.691,  45.280,  1.25,  0.09),  # Deneb          α Cyg
    (12.795, -59.688,  1.25, -0.22),  # Mimosa         β Cru
    (10.140,  11.967,  1.36, -0.11),  # Regulus        α Leo
    ( 6.977, -28.972,  1.50, -0.21),  # Adhara         ε CMa
    # ── mag 1.5–2.1 ────────────────────────────────────────────────────────
    ( 7.577,  31.888,  1.58,  0.04),  # Castor         α Gem
    (17.560, -37.103,  1.62, -0.22),  # Shaula         λ Sco
    (12.519, -57.113,  1.63,  1.60),  # Gacrux         γ Cru
    ( 5.419,   6.350,  1.64, -0.22),  # Bellatrix      γ Ori
    ( 5.438,  28.607,  1.68, -0.13),  # Elnath         β Tau
    ( 9.220, -69.717,  1.68,  0.07),  # Miaplacidus    β Car
    ( 5.603,  -1.202,  1.70, -0.19),  # Alnilam        ε Ori
    ( 5.679,  -1.943,  1.79, -0.20),  # Alnitak        ζ Ori
    ( 3.405,  49.861,  1.79,  0.48),  # Mirphak        α Per
    (11.062,  61.751,  1.81,  1.07),  # Dubhe          α UMa
    ( 7.140, -26.393,  1.84,  0.68),  # Wezen          δ CMa
    (18.403, -34.384,  1.85, -0.03),  # Kaus Australis ε Sgr
    ( 8.375, -59.509,  1.86,  1.26),  # Avior          ε Car
    (13.792,  49.313,  1.86, -0.19),  # Alkaid         η UMa
    (17.622, -42.998,  1.87,  0.41),  # Sargas         θ Sco
    (12.900,  55.960,  1.77,  0.02),  # Alioth         ε UMa
    ( 6.000,  44.947,  1.90,  0.03),  # Menkalinan     β Aur
    (16.811, -69.028,  1.92,  1.44),  # Atria          α TrA
    ( 6.629,  16.399,  1.93,  0.00),  # Alhena         γ Gem
    (20.427, -56.735,  1.94, -0.13),  # Peacock        α Pav
    ( 2.530,  89.264,  1.97,  0.60),  # Polaris        α UMi
    ( 8.745, -54.709,  1.96,  0.04),  # Alsephina      δ Vel
    ( 6.379, -17.956,  1.98, -0.24),  # Mirzam         β CMa
    (22.138, -46.961,  1.74, -0.13),  # Alnair         α Gru
    ( 9.460,  -8.659,  2.00,  1.44),  # Alphard        α Hya
    ( 2.120,  23.462,  2.01,  1.15),  # Hamal          α Ari
    (10.333,  19.841,  2.01,  1.13),  # Algieba        γ Leo
    ( 0.727, -17.987,  2.02,  1.02),  # Diphda         β Cet
    ( 1.162,  35.620,  2.06,  1.57),  # Mirach         β And
    (14.111, -36.370,  2.06,  1.01),  # Menkent        θ Cen
    ( 0.139,  29.091,  2.07,  0.10),  # Alpheratz      α And
    ( 5.796,  -9.670,  2.07, -0.17),  # Saiph          κ Ori
    (14.845,  74.156,  2.08,  1.47),  # Kochab         β UMi
    (17.582,  12.560,  2.08,  0.15),  # Rasalhague     α Oph
    (18.921, -26.297,  2.05, -0.13),  # Nunki          σ Sgr
    # ── mag 2.1–2.7 ────────────────────────────────────────────────────────
    (11.818,  14.572,  2.14,  0.09),  # Denebola       β Leo
    (12.692, -48.960,  2.17, -0.01),  # Muhlifain      γ Cen
    ( 9.133, -43.433,  2.21,  1.67),  # Suhail         λ Vel
    (15.578,  26.715,  2.23,  0.04),  # Alphecca       α CrB
    (20.371,  40.257,  2.23,  0.67),  # Sadr           γ Cyg
    ( 0.675,  56.537,  2.24,  1.17),  # Schedar        α Cas
    ( 8.060, -40.003,  2.25, -0.27),  # Naos           ζ Pup
    ( 9.285, -59.275,  2.25,  0.18),  # Aspidiske      ι Car
    ( 2.065,  42.330,  2.26,  1.37),  # Almach         γ And
    ( 0.153,  59.150,  2.27,  0.34),  # Caph           β Cas
    (13.399,  54.925,  2.27,  0.02),  # Mizar          ζ UMa
    (13.665, -53.466,  2.29, -0.22),  # ε Centauri
    (16.005, -22.622,  2.29, -0.12),  # Dschubba       δ Sco
    (16.836, -34.293,  2.29,  1.14),  # Wei            ε Sco
    (11.897,  53.695,  2.44,  0.03),  # Phecda         γ UMa
    (11.031,  56.382,  2.34,  0.02),  # Merak          β UMa
    (14.750,  27.074,  2.35,  0.97),  # Izar           ε Boo
    (21.736,   9.875,  2.38,  1.52),  # Enif           ε Peg
    ( 0.438, -42.306,  2.40,  1.09),  # Ankaa          α Phe
    (23.063,  28.083,  2.42,  1.67),  # Scheat         β Peg
    ( 7.402, -29.303,  2.45, -0.07),  # Aludra         η CMa
    (20.770,  33.970,  2.46,  1.03),  # Gienah Cyg     ε Cyg
    ( 9.368, -55.011,  2.47, -0.21),  # Markeb         κ Vel
    ( 5.546, -17.822,  2.58,  0.21),  # Arneb          α Lep
    (12.264, -17.542,  2.59, -0.11),  # Gienah Crv     γ Crv
    (15.284,  -9.383,  2.61, -0.10),  # Zubeneschamali β Lib
    (22.710, -46.885,  2.12,  1.62),  # β Gruis
    ( 5.661, -34.074,  2.65,  0.13),  # Phact          α Col
    (12.574, -23.397,  2.65,  0.89),  # Kraz           β Crv
    (15.737,   6.426,  2.63,  1.17),  # Unukalhai      α Ser
    (14.848, -16.042,  2.75,  0.15),  # Zubenelgenubi  α Lib
    # ── mag 2.7–3.5 ────────────────────────────────────────────────────────
    (16.503,  21.490,  2.78,  0.94),  # Kornephoros    β Her
    (12.694,  -1.449,  2.74,  0.36),  # Porrima        γ Vir
    (13.912,  18.398,  2.68,  0.58),  # Muphrid        η Boo
    (12.498, -16.515,  2.94, -0.03),  # Algorab        δ Crv
    (11.235,  20.524,  2.56,  0.13),  # Zosma          δ Leo
    (17.531, -37.296,  2.70, -0.17),  # Lesath         υ Sco
    (18.349, -29.828,  2.70,  1.38),  # Kaus Media     δ Sgr
    ( 2.530,  89.264,  1.97,  0.60),  # Polaris (dup guard — skip)
    (19.044, -29.880,  2.60,  0.08),  # Ascella        ζ Sgr
    (18.228, -25.422,  2.81,  1.04),  # Kaus Borealis  λ Sgr
    ( 3.136,  40.956,  2.12,  0.05),  # Algol          β Per
    (21.526,  -5.571,  2.91,  0.87),  # Sadalsuud      β Aqr
    ( 5.533,  -0.299,  2.23, -0.22),  # Mintaka        δ Ori
    (22.096,  -0.320,  2.96,  1.06),  # Sadalmelik     α Aqr
    (17.421, -55.530,  2.84,  1.47),  # β Arae
    (20.350, -14.781,  3.08,  0.79),  # Dabih          β Cap
    (17.244,  14.390,  3.48,  1.23),  # Rasalgethi     α Her
    ( 0.945,  60.717,  2.39,  0.13),  # γ Cassiopeiae
    ( 1.430,  60.235,  2.68,  0.13),  # Ruchbah        δ Cas
    ( 4.477,  19.180,  3.54,  1.01),  # Ain            ε Tau
    (12.257,  57.033,  3.31,  0.05),  # Megrez         δ UMa
    (16.682,  31.602,  2.81,  0.17),  # ζ Herculis
    (17.173, -15.725,  2.43,  0.06),  # Sabik          η Oph
    (16.304,  -4.692,  2.73,  1.32),  # Yed Prior      δ Oph
    (16.939, -10.567,  2.73,  0.02),  # Han            ζ Oph
    ( 3.791,  24.105,  2.85, -0.09),  # Alcyone        η Tau (Pleiades)
    ( 5.471, -20.759,  2.84,  0.82),  # Nihal          β Lep
    (22.833, -57.316,  2.83,  0.66),  # Alnair adj / θ Gru approx
    ( 7.452,   8.289,  2.89, -0.09),  # Gomeisa        β CMi
    ( 6.383,  22.514,  2.87,  1.64),  # Tejat          μ Gem
    (19.162, -21.024,  2.89,  0.06),  # Albaldah       π Sgr
    ( 7.960,  24.398,  3.00,  0.01),  # Propus         η Gem
    (16.091, -19.805,  2.50, -0.08),  # Graffias       β Sco
    (19.512,  27.960,  3.18,  1.00),  # Albireo        β Cyg
    (13.579,  11.162,  2.83,  0.24),  # Zaniah         η Vir
    (17.532, -49.876,  2.95, -0.05),  # α Arae
    (23.079,  15.184,  2.49, -0.01),  # Markab         α Peg
    ( 1.911,  20.808,  2.64,  0.09),  # Sheratan       β Ari
    (11.302,  31.529,  3.79,  0.72),  # Alula Aus      ξ UMa (skip — too faint)
    (10.167,  23.417,  3.43,  0.24),  # Adhafera       ζ Leo
    (11.237,  15.430,  3.34,  0.09),  # Chertan        θ Leo
    ( 6.728,  25.131,  2.99,  1.40),  # Mebsuda        ε Gem
    (20.190,  47.708,  2.87,  0.04),  # δ Cygni
    (20.295, -12.544,  3.57,  0.56),  # Algedi         α Cap
    (16.405,  -6.825,  2.77,  0.99),  # Yed Posterior  ε Oph
    (12.253, -58.749,  2.79, -0.13),  # δ Crucis
    ( 5.849, -35.768,  3.12,  1.10),  # Wazn           β Col
    (19.750,  45.131,  2.87,  0.04),  # δ Cygni (dup) — keep one
    ( 8.125, -24.304,  2.70,  0.24),  # Azmidiske      ξ Pup
    # Stars needed for constellation line endpoints
    ( 5.588,   9.934,  3.47, -0.28),  # Meissa      lam Ori
    (13.036,  10.959,  2.83,  0.80),  # Vindemiatrix eps Vir
    (14.534,  38.308,  3.03,  0.19),  # Seginus     gam Boo
    (19.771,  10.613,  2.72,  1.52),  # Tarazed     gam Aql
    (19.922,   6.407,  3.71,  0.86),  # Alshain     bet Aql
    (18.835,  33.363,  3.45,  0.00),  # Sheliak     bet Lyr
    (18.982,  32.690,  3.24,  0.10),  # Sulafat     gam Lyr
]

# ─── Constellation data ───────────────────────────────────────────────────────
# Each entry: (name, [polylines]).  Lines break at missing / below-horizon stars.
_CONSTELLATIONS = [
    ('Orion', [
        [(5.588,  9.934), (5.920,  7.407), (5.419,  6.350)],
        [(5.419,  6.350), (5.533, -0.299), (5.242, -8.202)],
        [(5.920,  7.407), (5.679, -1.943), (5.796, -9.670)],
        [(5.533, -0.299), (5.603, -1.202), (5.679, -1.943)],
    ]),
    ('Scorpius', [
        [(16.091,-19.805), (16.005,-22.622), (16.490,-26.432),
         (16.836,-34.293), (17.531,-37.296), (17.560,-37.103), (17.622,-42.998)],
    ]),
    ('Crux', [
        [(12.443,-63.099), (12.519,-57.113)],
        [(12.253,-58.749), (12.795,-59.688)],
    ]),
    ('Centaurus', [
        [(12.692,-48.960), (13.665,-53.466), (14.064,-60.373), (14.660,-60.833)],
        [(14.111,-36.370), (13.665,-53.466)],
    ]),
    ('Ursa Major', [
        [(11.062, 61.751), (11.031, 56.382), (11.897, 53.695), (12.257, 57.033), (11.062, 61.751)],
        [(12.257, 57.033), (12.900, 55.960), (13.399, 54.925), (13.792, 49.313)],
    ]),
    ('Leo', [
        [(10.167, 23.417), (10.333, 19.841), (10.140, 11.967),
         (11.237, 15.430), (11.235, 20.524), (10.333, 19.841)],
        [(11.235, 20.524), (11.818, 14.572)],
    ]),
    ('Sagittarius', [
        [(18.921,-26.297), (18.228,-25.422), (18.349,-29.828),
         (18.403,-34.384), (19.044,-29.880), (18.921,-26.297)],
        [(18.921,-26.297), (19.162,-21.024)],
    ]),
    ('Canis Major', [
        [(6.379,-17.956), (6.753,-16.716)],
        [(6.753,-16.716), (7.139,-26.393), (6.977,-28.972), (7.402,-29.303)],
        [(7.139,-26.393), (8.125,-24.304)],
    ]),
    ('Gemini', [
        [(7.577, 31.888), (7.755, 28.026)],
        [(7.577, 31.888), (6.629, 16.399)],
        [(7.755, 28.026), (6.728, 25.131), (6.383, 22.514)],
        [(6.383, 22.514), (6.629, 16.399)],
    ]),
    ('Taurus', [
        [(5.438, 28.607), (4.599, 16.509), (4.477, 19.180), (3.791, 24.105)],
    ]),
    ('Auriga', [
        [(5.278, 45.998), (6.000, 44.947), (5.438, 28.607), (5.278, 45.998)],
    ]),
    ('Virgo', [
        [(13.036, 10.959), (12.694, -1.449), (13.420,-11.161)],
    ]),
    ('Bootes', [
        [(13.912, 18.398), (14.261, 19.182), (14.750, 27.074), (14.534, 38.308)],
    ]),
    ('Cygnus', [
        [(20.691, 45.280), (20.371, 40.257), (19.512, 27.960)],
        [(19.750, 45.131), (20.371, 40.257), (20.770, 33.970)],
    ]),
    ('Aquila', [
        [(19.771, 10.613), (19.847,  8.868), (19.922,  6.407)],
    ]),
    ('Lyra', [
        [(18.616, 38.784), (18.835, 33.363), (18.982, 32.690)],
    ]),
    ('Cassiopeia', [
        [(0.153, 59.150), (0.675, 56.537), (0.945, 60.717), (1.430, 60.235)],
    ]),
    ('Perseus', [
        [(3.136, 40.956), (3.405, 49.861)],
    ]),
    ('Andromeda', [
        [(0.139, 29.091), (1.162, 35.620), (2.065, 42.330)],
    ]),
    ('Corvus', [
        [(12.264,-17.542), (12.498,-16.515), (12.574,-23.397), (12.264,-17.542)],
    ]),
    ('Hercules', [
        [(16.503, 21.490), (16.682, 31.602), (17.244, 14.390)],
        [(16.682, 31.602), (17.582, 12.560)],
    ]),
    ('Canis Minor', [
        [(7.452,  8.289), (7.655,  5.225)],
    ]),
    ('Corona Borealis', [
        [(15.578, 26.715), (14.750, 27.074)],
    ]),
]

def _seg_dist(px, py, ax, ay, bx, by):
    """Distance from point (px,py) to line segment (ax,ay)-(bx,by)."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax)*dx + (py - ay)*dy) / (dx*dx + dy*dy)))
    return math.hypot(px - ax - t*dx, py - ay - t*dy)

def _bv_to_rgb(bv):
    """Convert B-V color index to approximate RGB for star rendering."""
    if bv < -0.20: return (0.55, 0.65, 1.00)   # hot blue O/B
    if bv < -0.05: return (0.70, 0.82, 1.00)   # blue-white B/A
    if bv <  0.25: return (0.95, 0.96, 1.00)   # white A/F
    if bv <  0.58: return (1.00, 0.95, 0.75)   # yellow-white F/G
    if bv <  1.00: return (1.00, 0.80, 0.48)   # yellow-orange K
    if bv <  1.50: return (1.00, 0.58, 0.28)   # orange K/M
    return                (1.00, 0.38, 0.16)   # deep orange-red M

def _ra_dec_to_alt_az(ra_h, dec_deg, lat_deg, lon_deg, dt_utc):
    """Convert equatorial coordinates to local alt/az (J2000 approx)."""
    jd    = _julian_day(dt_utc)
    GMST  = (280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360
    LST   = (GMST + lon_deg) % 360
    HA    = math.radians((LST - ra_h * 15.0) % 360)
    dec   = math.radians(dec_deg)
    lat   = math.radians(lat_deg)
    sin_a = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(HA)
    alt   = math.degrees(math.asin(max(-1.0, min(1.0, sin_a))))
    cos_A = ((math.sin(dec) - math.sin(math.radians(alt)) * math.sin(lat))
             / (math.cos(math.radians(alt)) * math.cos(lat) + 1e-10))
    az    = math.degrees(math.acos(max(-1.0, min(1.0, cos_A))))
    if math.sin(HA) > 0:
        az = 360.0 - az
    return alt, az

_star_cache = {'key': None, 'data': []}

def _get_star_positions(lat, lon, dt_utc):
    """Compute and cache star alt/az positions (refreshed every minute)."""
    key = (round(lat, 3), round(lon, 3),
           dt_utc.year, dt_utc.month, dt_utc.day,
           dt_utc.hour, dt_utc.minute)
    if _star_cache['key'] == key:
        return _star_cache['data']
    data = []
    seen = set()
    for ra_h, dec_deg, mag, bv in _STARS:
        uid = (round(ra_h, 3), round(dec_deg, 3))
        if uid in seen:
            continue
        seen.add(uid)
        alt, az = _ra_dec_to_alt_az(ra_h, dec_deg, lat, lon, dt_utc)
        if alt > -1.0:   # include slightly below horizon (refraction)
            data.append((alt, az, mag, bv, ra_h, dec_deg))
    _star_cache['key']  = key
    _star_cache['data'] = data
    return data

# ─── Config ──────────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            for k, v in DEFAULT_CONFIG['cards'].items():
                if k not in cfg.get('cards', {}):
                    cfg.setdefault('cards', {})[k] = v
            for k in [k for k in list(cfg) if k not in DEFAULT_CONFIG]:
                del cfg[k]
            _set_lang(cfg.get('language', 'auto'))
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    cfg['cards'] = dict(DEFAULT_CONFIG['cards'])
    _set_lang('auto')
    return cfg

def save_config(cfg):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)

# ─── Autostart ───────────────────────────────────────────────────────────────

_AUTOSTART_PATH = os.path.expanduser('~/.config/autostart/caelum.desktop')
_SCRIPT_PATH    = os.path.abspath(__file__)

def set_autostart(enabled):
    if enabled:
        os.makedirs(os.path.dirname(_AUTOSTART_PATH), exist_ok=True)
        with open(_AUTOSTART_PATH, 'w') as f:
            f.write(
                '[Desktop Entry]\nType=Application\nName=Caelum\n'
                f'Exec=python3 {_SCRIPT_PATH}\nHidden=false\n'
                'NoDisplay=false\nX-GNOME-Autostart-enabled=true\n'
            )
    elif os.path.exists(_AUTOSTART_PATH):
        os.remove(_AUTOSTART_PATH)

def autostart_enabled():
    return os.path.exists(_AUTOSTART_PATH)

# ─── Astronomy ───────────────────────────────────────────────────────────────

def _julian_day(dt):
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jdn = (dt.day + (153 * m + 2) // 5 + 365 * y
           + y // 4 - y // 100 + y // 400 - 32045)
    return jdn + (dt.hour - 12) / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0

def solar_position(lat_deg, lon_deg, dt_utc):
    """Return (elevation°, azimuth°) for the sun."""
    lat = math.radians(lat_deg)
    n   = _julian_day(dt_utc) - 2451545.0
    L   = math.radians((280.46 + 0.9856474 * n) % 360)
    g   = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 4e-7 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))
    ra_h = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) / 15.0
    if ra_h < 0:
        ra_h += 24
    gmst = (18.697375 + 24.065709824279 * n) % 24
    ha   = math.radians(((gmst + lon_deg / 15.0) % 24 - ra_h) * 15)
    sin_el = (math.sin(lat) * math.sin(dec)
              + math.cos(lat) * math.cos(dec) * math.cos(ha))
    el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
    cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat))
              / (math.cos(math.radians(el)) * math.cos(lat) + 1e-10))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360.0 - az
    return el, az

def moon_position(lat_deg, lon_deg, dt_utc):
    """Return (elevation°, azimuth°) for the moon — Meeus Ch.47, ~0.3° accuracy."""
    lat = math.radians(lat_deg)
    jd  = _julian_day(dt_utc)
    T   = (jd - 2451545.0) / 36525.0

    D  = math.radians((297.8501921 + 445267.1114034 * T) % 360)
    M  = math.radians((357.5291092 +  35999.0502909 * T) % 360)
    Mp = math.radians((134.9633964 + 477198.8675055 * T) % 360)
    F  = math.radians(( 93.2720950 + 483202.0175233 * T) % 360)
    L0 = math.radians((218.3164477 + 481267.88123421 * T) % 360)

    dL = (6.288774 * math.sin(Mp)
        + 1.274027 * math.sin(2*D - Mp)
        + 0.658314 * math.sin(2*D)
        + 0.213618 * math.sin(2*Mp)
        - 0.185116 * math.sin(M)
        - 0.114332 * math.sin(2*F)
        + 0.058793 * math.sin(2*(D - Mp))
        + 0.057066 * math.sin(2*D - M - Mp)
        + 0.053322 * math.sin(2*D + Mp)
        + 0.045758 * math.sin(2*D - M))

    dB = (5.128122 * math.sin(F)
        + 0.280602 * math.sin(Mp + F)
        + 0.277693 * math.sin(Mp - F)
        + 0.173237 * math.sin(2*D - F)
        + 0.055413 * math.sin(2*D + F - Mp)
        + 0.046271 * math.sin(2*D - F - Mp)
        + 0.032573 * math.sin(2*D + F))

    lam  = L0 + math.radians(dL)
    beta = math.radians(dB)

    eps     = math.radians(23.4393 - 0.013004 * T)
    sin_dec = (math.sin(beta) * math.cos(eps)
               + math.cos(beta) * math.sin(eps) * math.sin(lam))
    dec = math.asin(max(-1.0, min(1.0, sin_dec)))
    ra  = math.atan2(
            math.sin(lam) * math.cos(beta) * math.cos(eps) - math.sin(beta) * math.sin(eps),
            math.cos(lam) * math.cos(beta))

    GMST = math.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)) % 360)
    ha   = GMST + math.radians(lon_deg) - ra

    sin_el = (math.sin(lat) * math.sin(dec)
              + math.cos(lat) * math.cos(dec) * math.cos(ha))
    el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
    cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat))
              / (math.cos(math.radians(el)) * math.cos(lat) + 1e-10))
    az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
    if math.sin(ha) > 0:
        az = 360.0 - az
    return el, az

def _find_event(lat, lon, date, tz_off, event):
    THRESHOLD = -0.833
    prev_el = None
    for m in range(1440):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = solar_position(lat, lon, utc)
        if prev_el is not None:
            if event == 'rise' and prev_el < THRESHOLD <= el:
                frac = (THRESHOLD - prev_el) / (el - prev_el)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
            if event == 'set' and prev_el > THRESHOLD >= el:
                frac = (prev_el - THRESHOLD) / (prev_el - el)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
        prev_el = el
    return None

def _find_moon_event(lat, lon, date, tz_off, event):
    """Scan the day at 1-min resolution to find moonrise or moonset."""
    prev_el = None
    for m in range(1440):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = moon_position(lat, lon, utc)
        if prev_el is not None:
            if event == 'rise' and prev_el < 0 <= el:
                frac = -prev_el / (el - prev_el + 1e-9)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
            if event == 'set' and prev_el > 0 >= el:
                frac = prev_el / (prev_el - el + 1e-9)
                tot  = m - 1 + frac
                return datetime.time(int(tot // 60) % 24, int(tot % 60))
        prev_el = el
    return None

def _solar_noon(lat, lon, date, tz_off):
    best_el, best_m = -90, 720
    for m in range(360, 960):
        h, mi = divmod(m, 60)
        utc = (datetime.datetime(date.year, date.month, date.day, h, mi)
               - datetime.timedelta(hours=tz_off))
        el, _ = solar_position(lat, lon, utc)
        if el > best_el:
            best_el, best_m = el, m
    return datetime.time(best_m // 60, best_m % 60), best_el

def moon_phase_age(dt_utc):
    known_new = datetime.datetime(2000, 1, 6, 18, 14)
    synodic   = 29.530588853
    delta     = (dt_utc - known_new).total_seconds() / 86400.0
    age       = delta % synodic
    return age / synodic, age

# ─── Planets ─────────────────────────────────────────────────────────────────

def _kepler_E(M_deg, e, tol=1e-6):
    M = math.radians(M_deg % 360)
    E = M
    for _ in range(100):
        dE = (M - E + e * math.sin(E)) / (1 - e * math.cos(E))
        E += dE
        if abs(dE) < tol:
            break
    return E

# Schlyter simplified orbital elements at J2000
# (a_AU, e, I_deg, N_deg, w_deg, M0_deg, M_rate_deg_per_day)
_PLANET_ELEMS = {
    'Mercury': (0.387098, 0.205635,  7.0050,  48.3313,  29.1241, 174.7948, 4.0923344368),
    'Venus':   (0.723330, 0.006773,  3.3946,  76.6799,  54.8910,  50.4161, 1.6021302244),
    'Mars':    (1.523688, 0.093405,  1.8497,  49.5574, 286.5016,  19.3730, 0.5240207766),
    'Jupiter': (5.202534, 0.048498,  1.3030, 100.4542, 273.8777,  19.8950, 0.0830853001),
    'Saturn':  (9.554909, 0.055509,  2.4847, 113.6634, 339.3939, 316.9670, 0.0334442282),
}

_PLANET_COLORS = {
    'Mercury': (0.85, 0.80, 0.75),
    'Venus':   (1.00, 0.95, 0.80),
    'Mars':    (1.00, 0.60, 0.35),
    'Jupiter': (1.00, 0.90, 0.70),
    'Saturn':  (0.95, 0.88, 0.65),
}

# Approximate average visual magnitudes — drives glow/disc radius scaling
_PLANET_MAG = {
    'Mercury':  0.0,
    'Venus':   -4.0,
    'Mars':    -1.0,
    'Jupiter': -2.2,
    'Saturn':   0.7,
}

_planet_cache = {'key': None, 'data': []}

def planet_positions(lat, lon, dt_utc):
    key = (round(lat, 3), round(lon, 3),
           dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour)
    if _planet_cache['key'] == key:
        return _planet_cache['data']

    jd    = _julian_day(dt_utc)
    d     = jd - 2451545.0
    GMST  = math.radians((280.46061837 + 360.98564736629 * d) % 360)
    lat_r = math.radians(lat)
    eps   = math.radians(23.4393 - 0.013004 * (d / 36525.0))

    # Sun's ecliptic position for geocentric conversion
    L_s   = math.radians((280.46 + 0.9856474 * d) % 360)
    g_s   = math.radians((357.528 + 0.9856003 * d) % 360)
    lam_s = (L_s + math.radians(1.915) * math.sin(g_s)
             + math.radians(0.020) * math.sin(2 * g_s))
    R_s   = 1.00014 - 0.01671 * math.cos(g_s) - 0.000140 * math.cos(2 * g_s)
    xs    = R_s * math.cos(lam_s)
    ys    = R_s * math.sin(lam_s)

    planets = []
    for name, (a, e, I, N, w, M0, M_rate) in _PLANET_ELEMS.items():
        M_deg = (M0 + M_rate * d) % 360
        E     = _kepler_E(M_deg, e)
        xv    = a * (math.cos(E) - e)
        yv    = a * math.sqrt(1.0 - e * e) * math.sin(E)
        v     = math.degrees(math.atan2(yv, xv))
        r     = math.sqrt(xv * xv + yv * yv)
        N_r   = math.radians(N)
        I_r   = math.radians(I)
        vw    = math.radians(v + w)
        # Heliocentric ecliptic
        xh = r * (math.cos(N_r) * math.cos(vw) - math.sin(N_r) * math.sin(vw) * math.cos(I_r))
        yh = r * (math.sin(N_r) * math.cos(vw) + math.cos(N_r) * math.sin(vw) * math.cos(I_r))
        zh = r * math.sin(vw) * math.sin(I_r)
        # Geocentric equatorial
        xg, yg, zg = xh + xs, yh + ys, zh
        xe = xg
        ye = yg * math.cos(eps) - zg * math.sin(eps)
        ze = yg * math.sin(eps) + zg * math.cos(eps)
        dist = math.sqrt(xe * xe + ye * ye + ze * ze) + 1e-30
        ra   = math.atan2(ye, xe)
        dec  = math.asin(max(-1.0, min(1.0, ze / dist)))
        ha   = GMST + math.radians(lon) - ra
        sin_el = (math.sin(lat_r) * math.sin(dec)
                  + math.cos(lat_r) * math.cos(dec) * math.cos(ha))
        el = math.degrees(math.asin(max(-1.0, min(1.0, sin_el))))
        cos_az = ((math.sin(dec) - math.sin(math.radians(el)) * math.sin(lat_r))
                  / (math.cos(math.radians(el)) * math.cos(lat_r) + 1e-10))
        az = math.degrees(math.acos(max(-1.0, min(1.0, cos_az))))
        if math.sin(ha) > 0:
            az = 360.0 - az
        planets.append((name, el, az, _PLANET_COLORS[name]))

    _planet_cache['key']  = key
    _planet_cache['data'] = planets
    return planets

# ─── Sky coordinate → screen ─────────────────────────────────────────────────

def sky_to_screen(el, az, W, H):
    """
    Panoramic projection: 240° wide, centred on _FACING azimuth.
    Returns None when body is below the horizon.
    """
    if el < 0:
        return None
    rel = ((az - _FACING + 180.0) % 360.0) - 180.0   # -180..+180, 0 = centre
    t   = _clamp((rel + 120.0) / 240.0, 0.0, 1.0)
    x   = W * 0.06 + t * (W * 0.88)
    y   = H * 0.72 - (H * 0.66) * _clamp(el / 90.0, 0.0, 1.0)
    return x, y

# ─── Weather ─────────────────────────────────────────────────────────────────

_WMO_PRECIP = {
    51: 0.2, 53: 0.5, 55: 1.2,
    56: 0.3, 57: 0.8,
    61: 0.4, 63: 1.5, 65: 4.0,
    66: 0.4, 67: 1.5,
    71: 0.3, 73: 0.8, 75: 2.0,
    80: 0.5, 81: 2.0, 82: 5.0,
    85: 0.3, 86: 1.0,
    95: 3.0, 96: 4.0, 99: 5.0,
}

def fetch_open_meteo(lat, lon):
    """Fetch cloud layers and precipitation from Open-Meteo (no key needed)."""
    url = (f"https://api.open-meteo.com/v1/forecast"
           f"?latitude={lat:.4f}&longitude={lon:.4f}"
           f"&current=cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high"
           f",precipitation,snowfall,weather_code")
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())
        c          = data['current']
        code       = int(c.get('weather_code', 0))
        raw_precip = float(c.get('precipitation', 0.0))
        precip     = raw_precip if raw_precip > 0 else _WMO_PRECIP.get(code, 0.0)
        snow       = float(c.get('snowfall', 0.0)) > 0.0 or code in (71, 73, 75, 77, 85, 86)
        total      = int(c.get('cloud_cover',     0))
        low        = int(c.get('cloud_cover_low',  0))
        mid        = int(c.get('cloud_cover_mid',  0))
        high       = int(c.get('cloud_cover_high', 0))
        if precip > 0 and total == 0:
            total = 60; low = 60
        return {
            'total': total, 'low': low, 'mid': mid, 'high': high,
            'precip': precip, 'snow': snow, 'wmo': code,
            'ts': c.get('time', ''),
        }
    except Exception:
        return None

# MET Norway symbol → approximate WMO code (for downstream logic)
_MET_SYMBOL_WMO = {
    'clearsky': 0, 'fair': 1, 'partlycloudy': 2, 'cloudy': 3,
    'fog': 45, 'lightrain': 61, 'rain': 63, 'heavyrain': 65,
    'lightsleet': 66, 'sleet': 67,
    'lightsnow': 71, 'snow': 73, 'heavysnow': 75,
    'lightrainshowers': 80, 'rainshowers': 81, 'heavyrainshowers': 82,
    'lightsnowshowers': 85, 'snowshowers': 86,
    'thunderstorm': 95, 'rainandthunder': 95, 'heavyrainandthunder': 99,
}

def fetch_met_norway(lat, lon):
    """Fetch from MET Norway LocationForecast 2.0 (no API key — User-Agent required)."""
    url = (f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
           f"?lat={lat:.4f}&lon={lon:.4f}")
    req = urllib.request.Request(url, headers={
        'User-Agent': 'caelum/1.0 https://github.com/Juliowilly/caelum'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        series  = data['properties']['timeseries']
        entry   = series[0]
        ts      = entry['time']
        instant = entry['data']['instant']['details']
        next1   = entry['data'].get('next_1_hours') or entry['data'].get('next_6_hours', {})
        symbol  = next1.get('summary', {}).get('symbol_code', '')
        symbol_base = symbol.split('_')[0] if symbol else ''
        precip  = float(next1.get('details', {}).get('precipitation_amount', 0.0))
        snow    = any(s in symbol_base for s in ('snow', 'sleet'))
        wmo     = _MET_SYMBOL_WMO.get(symbol_base, 0)

        # Hourly forecast: full timeseries (up to 4 days) + next-8 shortcut
        def _parse_hourly(fe):
            fi   = fe['data']['instant']['details']
            fn1  = fe['data'].get('next_1_hours') or fe['data'].get('next_6_hours', {})
            fsym = fn1.get('summary', {}).get('symbol_code', '')
            return {
                'ts':     fe['time'],
                'temp':   float(fi.get('air_temperature', 0.0)),
                'wind':   float(fi.get('wind_speed', 0.0)),
                'precip': float(fn1.get('details', {}).get('precipitation_amount', 0.0)),
                'symbol': (fsym.split('_')[0] if fsym else ''),
                'cloud':  int(fi.get('cloud_area_fraction', 0)),
            }
        forecast         = [_parse_hourly(fe) for fe in series[1:9]]
        hourly_forecast  = [_parse_hourly(fe) for fe in series[1:97]]

        # Daily forecast: group by UTC date, pick noon entry for symbol
        day_map = {}
        for fe in series:
            d = fe['time'][:10]
            day_map.setdefault(d, []).append(fe)
        daily_forecast = []
        for date_str in sorted(day_map.keys())[:8]:
            day_ents = day_map[date_str]
            noon = min(day_ents,
                       key=lambda e: abs(int(e['time'][11:13]) - 12))
            n12  = noon['data'].get('next_12_hours', {})
            n1   = noon['data'].get('next_1_hours', {})
            sym  = (n12.get('summary', {}).get('symbol_code') or
                    n1.get('summary', {}).get('symbol_code', ''))
            sym_b = sym.split('_')[0] if sym else ''
            temps  = [float(e['data']['instant']['details'].get('air_temperature', 0))
                      for e in day_ents]
            precip_sum = sum(
                float(e['data'].get('next_1_hours', {}).get('details', {})
                      .get('precipitation_amount', 0))
                for e in day_ents)
            daily_forecast.append({
                'date':     date_str,
                'temp_max': round(max(temps), 1) if temps else 0.0,
                'temp_min': round(min(temps), 1) if temps else 0.0,
                'symbol':   sym_b,
                'precip':   round(precip_sum, 1),
            })

        return {
            'total':      int(instant.get('cloud_area_fraction', 0)),
            'temp':       float(instant.get('air_temperature', 0.0)),
            'humidity':   float(instant.get('relative_humidity', 0.0)),
            'wind_speed': float(instant.get('wind_speed', 0.0)),
            'wind_dir':   float(instant.get('wind_from_direction', 0.0)),
            'precip':     precip,
            'snow':       snow,
            'wmo':        wmo,
            'symbol':         symbol_base,
            'ts':             ts,
            'forecast':        forecast,
            'hourly_forecast': hourly_forecast,
            'daily_forecast':  daily_forecast,
        }
    except Exception:
        return None

def merge_weather(om, met):
    """Merge Open-Meteo + MET Norway, taking the best of each source."""
    if om is None and met is None:
        return None
    result = dict(_NO_CLOUDS)
    if om is not None:
        result.update({
            'total': om['total'], 'low': om['low'],
            'mid':   om['mid'],   'high': om['high'],
            'precip': om['precip'], 'snow': om['snow'],
            'wmo': om['wmo'], 'ts': om.get('ts', ''),
        })
    if met is not None:
        # MET Norway: temperature, humidity, wind always preferred
        result['temp']       = met['temp']
        result['humidity']   = met['humidity']
        result['wind_speed'] = met['wind_speed']
        result['wind_dir']   = met['wind_dir']
        result['symbol']     = met['symbol']
        # Cloud total: average both sources for best estimate
        met_total = met['total']
        if om is not None:
            result['total'] = (om['total'] + met_total) // 2
        else:
            result['total'] = met_total
            result['low']   = 0; result['mid'] = met_total; result['high'] = 0
        # Precipitation: take the higher value (if either detects rain, show it)
        result['precip'] = max(result.get('precip', 0.0), met['precip'])
        if result['precip'] > 0 and result['total'] == 0:
            result['total'] = 60; result['low'] = 60
        # Snow: either source can detect it
        result['snow'] = result.get('snow', False) or met['snow']
        # WMO: prefer MET Norway when it has a specific code
        if met['wmo'] > 0:
            result['wmo'] = met['wmo']
        # Forecast and daily forecast come only from MET Norway
        result['forecast']        = met.get('forecast', [])
        result['hourly_forecast'] = met.get('hourly_forecast', [])
        result['daily_forecast']  = met.get('daily_forecast', [])
        # Combined timestamp for smart-skip: update when either source changes
        result['ts'] = (om.get('ts', '') if om else '') + '|' + met.get('ts', '')
    return result

# ─── Color helpers ────────────────────────────────────────────────────────────

def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(len(a)))

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

_SKY = {
    # No light pollution — true dark sky at night, natural transitions
    'night':    (0.00, 0.00, 0.04, 0.94),   # deep space black
    'astro':    (0.01, 0.01, 0.08, 0.86),
    'nautical': (0.03, 0.05, 0.18, 0.70),
    'civil':    (0.08, 0.06, 0.24, 0.54),
    'dawn':     (0.48, 0.18, 0.10, 0.38),
    'sunrise':  (0.82, 0.40, 0.06, 0.28),
    'morning':  (0.38, 0.60, 0.90, 0.20),
    'noon':     (0.16, 0.48, 0.96, 0.16),
    'afternoon':(0.26, 0.54, 0.92, 0.20),
    'sunset':   (0.78, 0.35, 0.07, 0.30),
    'dusk':     (0.32, 0.10, 0.22, 0.52),
}

def sky_color(el):
    S = _SKY
    if el < -18:   return S['night']
    if el < -12:   return _lerp(S['night'],    S['astro'],    (el + 18) / 6)
    if el < -6:    return _lerp(S['astro'],    S['nautical'], (el + 12) / 6)
    if el < -0.83: return _lerp(S['nautical'], S['civil'],    (el + 6)  / 5.17)
    if el < 3:     return _lerp(S['civil'],    S['dawn'],     (el + 0.83) / 3.83)
    if el < 8:     return _lerp(S['dawn'],     S['sunrise'],  (el - 3)  / 5)
    if el < 20:    return _lerp(S['sunrise'],  S['morning'],  (el - 8)  / 12)
    if el < 50:    return _lerp(S['morning'],  S['noon'],     (el - 20) / 30)
    return S['noon']

def sky_color_adaptive(el, clouds, m_bright):
    r, g, b, a = sky_color(el)
    cf = clouds['total'] / 100.0
    r = r + (0.50 - r) * cf * 0.40
    g = g + (0.50 - g) * cf * 0.38
    b = b + (0.50 - b) * cf * 0.32
    a = min(0.72, a + cf * 0.12)
    if el < -0.83 and m_bright > 0.35:
        mf = (m_bright - 0.35) / 0.65
        r = r + (0.12 - r) * mf * 0.18
        g = g + (0.16 - g) * mf * 0.18
        b = b + (0.32 - b) * mf * 0.28
        a = min(0.72, a + mf * 0.05)
    return r, g, b, a

def moon_brightness(phase, m_el):
    illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
    return illumination * _clamp((m_el + 10) / 40.0, 0, 1)

# ─── Cloud palette by sun elevation ──────────────────────────────────────────

def _cloud_palette(sun_el):
    """Return (top_rgb, dark_rgb, cirrus_rgb) tuned for no light pollution."""
    if sun_el > 20:   # midday: blinding white tops, steel-blue undersides
        return (1.00, 1.00, 1.00), (0.58, 0.64, 0.76), (0.90, 0.94, 1.00)
    if sun_el > 5:    # morning/afternoon: ivory tops, warm gray undersides
        t   = (sun_el - 5) / 15.0
        top = (1.00, 0.92 + t * 0.08, 0.78 + t * 0.22)
        drk = (0.56 + t * 0.06, 0.52 + t * 0.10, 0.44 + t * 0.24)
        cir = (0.96, 0.92 + t * 0.04, 0.80 + t * 0.20)
        return top, drk, cir
    if sun_el > -2:   # golden hour: salmon-pink, not fire — tropical look
        t   = (sun_el + 2) / 7.0
        top = (1.00, 0.62 + t * 0.30, 0.38 + t * 0.40)
        drk = (0.42 + t * 0.14, 0.22 + t * 0.30, 0.18 + t * 0.26)
        cir = (1.00, 0.72 + t * 0.20, 0.48 + t * 0.32)
        return top, drk, cir
    if sun_el > -10:  # twilight: lavender fading to violet-gray
        t   = (sun_el + 10) / 8.0
        top = (0.40 + t * 0.60, 0.30 + t * 0.32, 0.50 + t * 0.50)
        drk = (0.18 + t * 0.24, 0.14 + t * 0.08, 0.26 + t * 0.18)
        cir = (0.46 + t * 0.54, 0.38 + t * 0.34, 0.56 + t * 0.44)
        return top, drk, cir
    # Full night — silver-gray, faintly blue (starlight)
    return (0.32, 0.35, 0.50), (0.16, 0.18, 0.30), (0.36, 0.38, 0.54)

# ─── Cloud rendering ─────────────────────────────────────────────────────────

def _soft_puff(cr, cx, cy, rx, ry, r, g, b, alpha):
    """Soft elliptical cloud puff with natural liquid-water-content density profile."""
    if rx <= 0 or ry <= 0 or alpha <= 0:
        return
    cr.save()
    cr.translate(cx, cy)
    cr.scale(rx, ry)
    pat = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    pat.add_color_stop_rgba(0.00, r, g, b, alpha)
    pat.add_color_stop_rgba(0.28, r, g, b, alpha * 0.92)  # dense core
    pat.add_color_stop_rgba(0.58, r, g, b, alpha * 0.50)
    pat.add_color_stop_rgba(0.82, r, g, b, alpha * 0.12)  # sharp edge falloff
    pat.add_color_stop_rgba(1.00, r, g, b, 0.0)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.set_source(pat)
    cr.fill()
    cr.restore()

def _draw_overcast_sheet(cr, W, H, total, top_col, dark_col):
    """Uniform gray ceiling for heavily overcast skies (total > 65%)."""
    t  = _clamp((total - 65) / 35.0, 0.0, 1.0)
    rt, gt, bt = top_col
    rd, gd, bd = dark_col
    sr = (rd + rt) * 0.52;  sg = (gd + gt) * 0.52;  sb = (bd + bt) * 0.54
    y0    = H * 0.72
    alpha = t * 0.52
    grad  = cairo.LinearGradient(0, 0, 0, y0)
    grad.add_color_stop_rgba(0.00, sr, sg, sb, alpha * 0.95)
    grad.add_color_stop_rgba(0.38, sr, sg, sb, alpha * 0.85)
    grad.add_color_stop_rgba(0.72, sr, sg, sb, alpha * 0.35)
    grad.add_color_stop_rgba(1.00, sr, sg, sb, 0.0)
    cr.rectangle(0, 0, W, y0)
    cr.set_source(grad)
    cr.fill()

def draw_cirrus(cr, W, H, coverage, col, rng):
    """High-altitude ice clouds: thin wispy streaks with fade envelope and parallel fibers."""
    if coverage < 5:
        return
    r, g, b = col
    n      = int(coverage / 100.0 * 10) + 1
    a_base = 0.08 + 0.13 * (coverage / 100.0)

    for _ in range(n):
        cx     = rng.uniform(0.03, 0.97) * W
        cy     = rng.uniform(0.02, 0.26) * H
        length = rng.uniform(0.08, 0.30) * W
        thick  = rng.uniform(0.005, 0.013) * H
        tilt   = rng.uniform(-0.22, 0.22)
        n_seg  = rng.randint(7, 13)
        curve  = rng.uniform(-0.08, 0.08) * length  # gentle hook curvature

        # Main streak — alpha envelope bright at centre, fading at both ends
        for j in range(n_seg):
            t   = j / max(1, n_seg - 1)
            env = 1.0 - (abs(t - 0.5) * 2) ** 1.6
            sx  = cx + (t - 0.5) * length * math.cos(tilt)
            sy  = (cy + (t - 0.5) * length * math.sin(tilt)
                   + rng.uniform(-thick, thick)
                   + curve * (t - 0.5) ** 2)   # slight curve toward one end
            sw  = length / n_seg * 1.9 * rng.uniform(0.6, 1.4)
            sh  = thick * rng.uniform(0.6, 1.8)
            _soft_puff(cr, sx, sy, sw, sh, r, g, b, a_base * rng.uniform(0.5, 1.0) * env)

        # Parallel fiber ghost (mare's tails character)
        if rng.random() < 0.65:
            off = rng.uniform(0.6, 1.8) * thick * 2
            for j in range(n_seg // 2):
                t   = j / max(1, n_seg // 2 - 1)
                env = 1.0 - (abs(t - 0.5) * 2) ** 1.4
                sx  = cx + (t - 0.5) * length * 0.68 * math.cos(tilt)
                sy  = cy + off + (t - 0.5) * length * 0.68 * math.sin(tilt)
                _soft_puff(cr, sx, sy,
                           length / n_seg * 1.2, thick * 0.65,
                           r, g, b, a_base * 0.38 * env)

def draw_altocumulus(cr, W, H, coverage, col, rng):
    """Mid-level clouds: compact rounded puffs with lit top and shadowed underside."""
    if coverage < 5:
        return
    r, g, b = col
    rs, gs, bs = r * 0.68, g * 0.70, b * 0.72   # shadow underside colour
    n      = int(coverage / 100.0 * 24) + 3
    a_base = 0.70 + 0.28 * (coverage / 100.0)

    for _ in range(n):
        cx = rng.uniform(0.02, 0.98) * W
        cy = rng.uniform(0.08, 0.58) * H
        cw = rng.uniform(0.022, 0.062) * W
        ch = rng.uniform(0.012, 0.030) * H
        a  = a_base * rng.uniform(0.65, 1.00)

        for _ in range(rng.randint(2, 4)):
            ox = rng.uniform(-cw * 0.38, cw * 0.38)
            oy = rng.uniform(-ch * 0.28, ch * 0.05)
            pw = cw * rng.uniform(0.35, 0.72)
            ph = ch * rng.uniform(0.58, 1.10)
            _soft_puff(cr, cx + ox, cy + oy, pw, ph,
                       r, g, b, a * rng.uniform(0.72, 1.00))
            # Shadow underside: darker, flatter, slightly below centre
            _soft_puff(cr, cx + ox, cy + oy + ph * 0.30, pw * 0.85, ph * 0.20,
                       rs, gs, bs, a * 0.30)

def draw_cumulus(cr, W, H, coverage, top_col, dark_col, rng, wmo=0):
    """
    Low cumulus: crisp flat base, cauliflower puff tower, specular highlight,
    ground shadow. Cumulonimbus anvil for thunderstorm WMO codes (≥95).
    """
    if coverage < 5:
        return
    rt, gt, bt = top_col
    rd, gd, bd = dark_col
    is_cb = wmo >= 95
    n      = int(coverage / 100.0 * 8) + 1
    a_base = 0.48 + 0.42 * (coverage / 100.0)

    for i in range(n):
        cx = rng.uniform(0.04, 0.96) * W
        # Cloud base sits near the horizon (LCL level)
        base_y = rng.uniform(0.54, 0.70) * H
        if is_cb and i == 0:
            cw = rng.uniform(0.18, 0.34) * W
            ch = rng.uniform(0.20, 0.34) * H
        else:
            cw = rng.uniform(0.07, 0.21) * W
            ch = rng.uniform(0.06, 0.13) * H

        # 1. Ground shadow — faint dark ellipse on terrain for large nearby clouds
        if base_y > 0.60 * H:
            _soft_puff(cr, cx, H * 0.73,
                       cw * 0.50, H * 0.010,
                       rd * 0.45, gd * 0.45, bd * 0.50,
                       a_base * 0.20)

        # 2. Flat dark base — wide, horizontally compressed (the cloud's LCL line)
        _soft_puff(cr, cx, base_y, cw * 1.08, ch * 0.16,
                   rd, gd, bd, a_base * 0.90)
        _soft_puff(cr, cx, base_y - ch * 0.05, cw * 0.95, ch * 0.09,
                   rd, gd, bd, a_base * 0.55)   # sharp inner edge

        # 3. Main body — several overlapping puffs rising from the base
        n_body = rng.randint(4, 7)
        for j in range(n_body):
            ox  = (j / max(1, n_body - 1) - 0.5) * cw * 0.80
            dim = 1.0 - abs(ox / (cw * 0.5)) * 0.14   # edge puffs slightly darker
            _soft_puff(cr,
                       cx + ox, base_y + rng.uniform(-ch * 0.18, ch * 0.06),
                       cw * rng.uniform(0.28, 0.54),
                       ch * rng.uniform(0.55, 0.92),
                       rt * dim, gt * dim, bt * dim,
                       a_base * rng.uniform(0.80, 1.00))

        # 4. Cauliflower second tier — smaller puffs on top
        n_top = rng.randint(2, 5)
        for j in range(n_top):
            ox = (j / max(1, n_top - 1) - 0.5) * cw * 0.55
            _soft_puff(cr,
                       cx + ox, base_y - ch * rng.uniform(0.38, 0.72),
                       cw * rng.uniform(0.18, 0.36),
                       ch * rng.uniform(0.30, 0.55),
                       rt, gt, bt, a_base * rng.uniform(0.65, 0.90))

        # 5. Bright sunlit specular highlight at the very top
        _soft_puff(cr,
                   cx + rng.uniform(-cw * 0.10, cw * 0.10),
                   base_y - ch * rng.uniform(0.62, 0.90),
                   cw * 0.20, ch * 0.26,
                   min(1.0, rt + 0.07), min(1.0, gt + 0.05), min(1.0, bt + 0.02),
                   a_base * 0.60)

        # 6. Cumulonimbus anvil — flat spreading top for thunderstorm clouds
        if is_cb and i == 0:
            anvil_y = base_y - ch * 0.88
            _soft_puff(cr, cx, anvil_y, cw * 1.55, ch * 0.16,
                       rd * 0.75, gd * 0.75, bd * 0.80, a_base * 0.70)
            _soft_puff(cr, cx, anvil_y - ch * 0.06, cw * 1.35, ch * 0.10,
                       rd * 0.65, gd * 0.65, bd * 0.72, a_base * 0.45)

# ─── Window ───────────────────────────────────────────────────────────────────

class SkyTracker(Gtk.Window):

    def __init__(self):
        super().__init__()
        self.cfg      = load_config()
        self._sunrise = self._sunset = self._s_noon = None
        self._max_el  = 0.0
        self._last_date    = None
        self._settings_win = None
        self._clouds           = dict(_NO_CLOUDS)
        self._last_weather_ts  = ''   # Open-Meteo 'current.time'; changes every 15 min
        self._hover_const  = None
        self._star_screen_cache = {}
        self._mouse_x = self._mouse_y = -1
        self._gear_cx = self._gear_cy = 0
        self._selected_day       = None   # date string 'YYYY-MM-DD' of clicked weekly card
        self._selected_day_slots = []     # hourly slots for selected day (cached in _on_click)
        self._weekly_card_rects  = []     # [(date_str, x, y, w, h), ...]
        self._city_name          = None   # reverse-geocoded city name
        self._moon_limb_angle    = 0.0    # stored each frame for use in info card icon
        self._today_str          = datetime.date.today().isoformat()
        self._astro_cache        = None   # (sun_el, sun_az, m_el, m_az, phase, age, m_bright)
        self._astro_cache_t      = 0.0    # time.monotonic() of last astro recalc
        self._weather_fetching   = False  # dedup flag for _fetch_weather_async
        self._cmp_cx  = 62
        self._cmp_cy  = 95
        self._cmp_r   = 46
        self._moonrise = self._moonset = None
        self._meteors  = []
        self._hw_heading   = None   # live heading from hardware sensor (degrees)
        self._has_compass  = False
        self._compass_dev  = None   # IIO sysfs device path
        self._detect_compass()

        self._setup_window()
        self._refresh_day()
        self._fetch_weather_async()
        self._fetch_city_name()
        GLib.timeout_add(100,             self._tick)
        GLib.timeout_add(60 * 1000,       self._fetch_weather_async)
        GLib.timeout_add(5 * 60 * 1000,  self._export_lockscreen_bg)
        if self._has_compass:
            GLib.timeout_add(500, self._poll_compass)

    # ── Hardware compass ─────────────────────────────────────────────────────

    def _detect_compass(self):
        """Probe for a magnetometer — IIO sysfs, D-Bus, or USB serial."""
        # Close any previous serial connection
        if hasattr(self, '_serial_compass') and self._serial_compass:
            try:
                self._serial_compass.close()
            except Exception:
                pass
            self._serial_compass = None

        self._has_compass  = False
        self._compass_dev  = None
        self._compass_src  = None   # 'iio' | 'dbus' | 'serial' | 'url'
        self._compass_status = 'Not detected'

        # Method 1: IIO sysfs (works without any daemon)
        for dev in glob.glob('/sys/bus/iio/devices/iio:device*'):
            xf = os.path.join(dev, 'in_magn_x_raw')
            yf = os.path.join(dev, 'in_magn_y_raw')
            if os.path.exists(xf) and os.path.exists(yf):
                self._compass_dev    = dev
                self._has_compass    = True
                self._compass_src    = 'iio'
                self._compass_status = 'IIO sensor active'
                return

        # Method 2: iio-sensor-proxy via D-Bus
        try:
            import dbus
            bus  = dbus.SystemBus()
            prox = bus.get_object('net.hadess.SensorProxy', '/net/hadess/SensorProxy')
            dbus.Interface(prox, 'net.hadess.SensorProxy').ClaimCompass()
            self._dbus_sensor_proxy = prox
            self._has_compass    = True
            self._compass_src    = 'dbus'
            self._compass_status = 'iio-sensor-proxy active'
            return
        except Exception:
            pass

        # Method 3: external USB/serial compass (Arduino, USB dongle, etc.)
        port = self.cfg.get('compass_port', '').strip()
        if port:
            try:
                import serial as _serial
                ser = _serial.Serial(port, baudrate=9600, timeout=1)
                # Quick read to verify it responds with a float heading
                line = ser.readline().decode(errors='ignore').strip()
                float(line)   # raises if not a number
                self._serial_compass = ser
                self._has_compass    = True
                self._compass_src    = 'serial'
                self._compass_status = f'Serial: {port}'
            except ImportError:
                self._compass_status = 'pyserial not installed (pip3 install pyserial)'
            except Exception as e:
                self._compass_status = f'Serial error: {e}'

    def _poll_compass(self):
        """Read compass heading; called every 500 ms via GLib timer."""
        if not self._has_compass:
            return False
        def _work():
            hdg = None
            src = getattr(self, '_compass_src', None)
            if src == 'iio' and self._compass_dev:
                try:
                    x  = float(open(f'{self._compass_dev}/in_magn_x_raw').read())
                    y  = float(open(f'{self._compass_dev}/in_magn_y_raw').read())
                    sf = os.path.join(self._compass_dev, 'in_magn_x_scale')
                    sc = float(open(sf).read()) if os.path.exists(sf) else 1.0
                    hdg = (math.degrees(math.atan2(-y * sc, x * sc)) + 360) % 360
                except Exception:
                    pass
            elif src == 'dbus' and hasattr(self, '_dbus_sensor_proxy'):
                try:
                    import dbus
                    props = dbus.Interface(self._dbus_sensor_proxy,
                                          'org.freedesktop.DBus.Properties')
                    hdg = float(props.Get('net.hadess.SensorProxy.Compass',
                                         'CompassHeading'))
                except Exception:
                    pass
            elif src == 'serial' and hasattr(self, '_serial_compass'):
                try:
                    line = self._serial_compass.readline().decode(
                        errors='ignore').strip()
                    if line:
                        hdg = float(line) % 360
                except Exception:
                    pass
            if hdg is not None:
                GLib.idle_add(self._apply_heading, hdg)
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _apply_heading(self, hdg):
        self._hw_heading = hdg
        return False

    # ── Window setup ─────────────────────────────────────────────────────────

    def _setup_window(self):
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        if self.cfg.get('sticky', True):
            self.stick()
        if self.cfg.get('keep_above', False):
            self.set_keep_above(True)

        self.da = Gtk.DrawingArea()
        self.da.connect('draw', self._on_draw)
        self.da.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        self.da.connect('motion-notify-event', self._on_motion)
        self.add(self.da)

        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.set_can_focus(True)
        self.connect('key-press-event', self._on_key)
        self.connect('button-press-event', self._on_click)

        self.show_all()
        GLib.idle_add(self._force_fullscreen)
        GLib.timeout_add(500, self._force_fullscreen)

    def _force_fullscreen(self):
        display = self.get_screen().get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        if monitor:
            geo = monitor.get_geometry()
            self.move(geo.x, geo.y)
            self.resize(geo.width, geo.height)
        return False

    # ── Day data ─────────────────────────────────────────────────────────────

    def _refresh_day(self):
        self._last_date  = datetime.date.today()   # prevent re-entry from _tick
        self._today_str  = self._last_date.isoformat()
        cfg = self.cfg
        lat = cfg['latitude']; lon = cfg['longitude']; tz = cfg['timezone_offset']
        today = self._last_date
        def _work():
            sunrise  = _find_event(lat, lon, today, tz, 'rise')
            sunset   = _find_event(lat, lon, today, tz, 'set')
            s_noon, max_el = _solar_noon(lat, lon, today, tz)
            moonrise = _find_moon_event(lat, lon, today, tz, 'rise')
            moonset  = _find_moon_event(lat, lon, today, tz, 'set')
            def _apply():
                self._sunrise  = sunrise
                self._sunset   = sunset
                self._s_noon   = s_noon
                self._max_el   = max_el
                self._moonrise = moonrise
                self._moonset  = moonset
                self.da.queue_draw()
                return False
            GLib.idle_add(_apply)
        threading.Thread(target=_work, daemon=True).start()

    def _tick(self):
        if datetime.date.today() != self._last_date:
            self._refresh_day()
        self.da.queue_draw()
        return True

    # ── Weather ──────────────────────────────────────────────────────────────

    def _fetch_weather_async(self):
        if self._weather_fetching:
            return True
        self._weather_fetching = True
        lat, lon = self.cfg['latitude'], self.cfg['longitude']
        need_city = (self._city_name is None)
        def _work():
            buf = [None, None]
            def _om():  buf[0] = fetch_open_meteo(lat, lon)
            def _met(): buf[1] = fetch_met_norway(lat, lon)
            t1 = threading.Thread(target=_om,  daemon=True)
            t2 = threading.Thread(target=_met, daemon=True)
            t1.start(); t2.start()
            t1.join(timeout=12); t2.join(timeout=12)
            merged = merge_weather(buf[0], buf[1])
            if merged is not None:
                GLib.idle_add(self._apply_clouds, merged)
            GLib.idle_add(self._clear_weather_fetching)
            if need_city:
                GLib.idle_add(self._fetch_city_name)
        threading.Thread(target=_work, daemon=True).start()
        return True

    def _clear_weather_fetching(self):
        self._weather_fetching = False
        return False

    def _fetch_city_name(self):
        """Reverse-geocode current coordinates via Nominatim (once at startup)."""
        lat = self.cfg['latitude']
        lon = self.cfg['longitude']
        def _work():
            try:
                url = (f"https://nominatim.openstreetmap.org/reverse"
                       f"?format=json&lat={lat:.4f}&lon={lon:.4f}&zoom=10")
                req = urllib.request.Request(url, headers={
                    'User-Agent': 'caelum/1.0 github.com/Juliowilly/caelum'
                })
                with urllib.request.urlopen(req, timeout=8) as r:
                    data = json.loads(r.read())
                addr = data.get('address', {})
                city = (addr.get('city') or addr.get('town') or
                        addr.get('village') or addr.get('municipality') or
                        addr.get('county') or '')
                country = addr.get('country', '')
                name = f"{city}, {country}" if city and country else city or country or ''
                GLib.idle_add(self._set_city_name, name)
            except Exception:
                pass
        threading.Thread(target=_work, daemon=True).start()

    def _set_city_name(self, name):
        self._city_name = name
        self.da.queue_draw()
        return False

    def _apply_clouds(self, value):
        ts = value.get('ts', '')
        if ts and ts == self._last_weather_ts:
            return False   # same 15-min slot — nothing changed, skip redraw
        self._last_weather_ts = ts
        self._clouds = value
        if self._selected_day:
            all_h = value.get('hourly_forecast', [])
            self._selected_day_slots = [
                s for s in all_h if s.get('ts', '')[:10] == self._selected_day
            ][:8]
        self.da.queue_draw()
        return False

    # ── Event handlers ───────────────────────────────────────────────────────

    def _on_key(self, _w, ev):
        ctrl = ev.state & Gdk.ModifierType.CONTROL_MASK
        k    = ev.keyval
        if ctrl and k in (ord('h'), ord('H')):
            self.cfg['clean_mode'] = not self.cfg.get('clean_mode', False)
            save_config(self.cfg)
            self.da.queue_draw()
            return True
        if ctrl and k in (ord('s'), ord('S')):
            self._open_settings()
            return True
        if ctrl and k in (ord('q'), ord('Q')):
            Gtk.main_quit()
            return True
        return False

    def _on_click(self, _w, ev):
        if math.hypot(ev.x - self._gear_cx, ev.y - self._gear_cy) <= 20:
            self._open_settings()
            return True
        if (self.cfg.get('show_compass', True) and self._hw_heading is None
                and math.hypot(ev.x - self._cmp_cx, ev.y - self._cmp_cy) <= self._cmp_r):
            # Click inside compass rose → angle from centre = new facing direction
            dx = ev.x - self._cmp_cx
            dy = ev.y - self._cmp_cy
            # atan2 with y-down screen: angle 0=up=North, clockwise positive
            facing = (math.degrees(math.atan2(dx, -dy)) + 360) % 360
            self.cfg['facing'] = round(facing, 1)
            save_config(self.cfg)
            self.da.queue_draw()
            return True
        # Click on a weekly forecast day card
        if self.cfg.get('show_weekly_forecast', True):
            for date_str, rx, ry, rw, rh in self._weekly_card_rects:
                if rx <= ev.x <= rx + rw and ry <= ev.y <= ry + rh:
                    if self._selected_day == date_str:
                        self._selected_day       = None
                        self._selected_day_slots = []
                    else:
                        self._selected_day = date_str
                        all_h = self._clouds.get('hourly_forecast', [])
                        self._selected_day_slots = [
                            s for s in all_h if s.get('ts', '')[:10] == date_str
                        ][:8]
                    self.da.queue_draw()
                    return True
        if ev.button == 3:
            self._open_settings()
            return True
        # Left-click outside everything deselects the day
        if ev.button == 1 and self._selected_day is not None:
            self._selected_day = None
            self.da.queue_draw()
        return False

    def _on_motion(self, _w, ev):
        self._mouse_x, self._mouse_y = ev.x, ev.y
        if self.cfg.get('show_constellations', True) and self._star_screen_cache:
            new_hover = self._hit_test_constellation(ev.x, ev.y)
        else:
            new_hover = None
        if new_hover != self._hover_const:
            self._hover_const = new_hover
            self.da.queue_draw()
        # Compass hover — only when no hardware heading (manual mode)
        over_cmp = (self.cfg.get('show_compass', True)
                    and self._hw_heading is None
                    and math.hypot(ev.x - self._cmp_cx, ev.y - self._cmp_cy) <= self._cmp_r)
        if over_cmp != getattr(self, '_hover_compass', False):
            self._hover_compass = over_cmp
            win = self.get_window()
            if win:
                win.set_cursor(
                    Gdk.Cursor.new_from_name(self.get_display(),
                                             'crosshair' if over_cmp else 'default'))
            self.da.queue_draw()

    def _hit_test_constellation(self, mx, my):
        threshold = 22.0
        for name, polylines in _CONSTELLATIONS:
            for polyline in polylines:
                pts = [self._star_screen_cache.get((round(r, 2), round(d, 1)))
                       for r, d in polyline]
                for i in range(len(pts) - 1):
                    a, b = pts[i], pts[i + 1]
                    if a is None or b is None:
                        continue
                    if _seg_dist(mx, my, a[0], a[1], b[0], b[1]) < threshold:
                        return name
        return None

    def _open_settings(self):
        if self._settings_win and self._settings_win.get_visible():
            self._settings_win.present()
            return
        self._settings_win = SettingsDialog(self)
        self._settings_win.show_all()

    # ── Draw dispatch ────────────────────────────────────────────────────────

    def _on_draw(self, _w, cr):
        global _FACING
        cfg   = self.cfg
        alloc = self.da.get_allocation()
        W, H  = alloc.width, alloc.height

        _FACING = (float(self._hw_heading)
                   if self._hw_heading is not None
                   else float(cfg.get('facing', 180.0)))

        utc    = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        now    = utc + datetime.timedelta(hours=cfg['timezone_offset'])
        lat, lon = cfg['latitude'], cfg['longitude']
        scale  = cfg.get('aster_scale', 1.0)
        clean  = cfg.get('clean_mode', False)

        t_now = time.monotonic()
        if self._astro_cache is None or t_now - self._astro_cache_t >= 1.0:
            sun_el, sun_az = solar_position(lat, lon, utc)
            m_el,   m_az   = moon_position(lat, lon, utc)
            phase,  age    = moon_phase_age(utc)
            m_bright       = moon_brightness(phase, m_el)
            self._astro_cache   = (sun_el, sun_az, m_el, m_az, phase, age, m_bright)
            self._astro_cache_t = t_now
        else:
            sun_el, sun_az, m_el, m_az, phase, age, m_bright = self._astro_cache

        # ── Cloud occlusion visibility factors ───────────────────────────────
        cld_total = self._clouds.get('total', 0)
        # Sun: always retains a faint diffuse glow through overcast
        sun_vis  = max(0.10, 1.0 - _clamp((cld_total - 10) / 75.0, 0.0, 1.0))
        # Moon: dims a bit faster than the sun
        moon_vis = max(0.04, 1.0 - _clamp((cld_total - 15) / 70.0, 0.0, 1.0))
        # Stars and planets vanish completely behind thick cloud
        sky_vis  = 1.0 - _clamp((cld_total - 20) / 65.0, 0.0, 1.0)

        # ── Gear button is always drawn first (visible even when app is off)
        gx, gy = W - 28, H - 28
        self._gear_cx, self._gear_cy = gx, gy
        app_on = cfg.get('app_enabled', True)

        if not app_on:
            # Clear to transparent, show only the gear button in red-tinted "off" state
            cr.set_operator(cairo.Operator.SOURCE)
            cr.set_source_rgba(0, 0, 0, 0)
            cr.paint()
            cr.set_operator(cairo.Operator.OVER)
            self._draw_gear_btn(cr, gx, gy, 16, off=True)
            return

        # ── sky gradient + clouds (clouds need body positions for glow)
        self._draw_sky(cr, W, H, sun_el, sun_az, m_el, m_az, self._clouds, m_bright,
                       lat, lon, utc)

        # ── sun (show once above ~-2° so horizon glow is visible)
        if sun_el > -2:
            pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
            if pos:
                use_group = sun_vis < 0.999
                if use_group:
                    cr.push_group()
                self._draw_crepuscular_rays(cr, W, H, sun_el, sun_az, scale)
                self._draw_sun(cr, pos[0], pos[1], sun_el, scale)
                if use_group:
                    cr.pop_group_to_source()
                    cr.paint_with_alpha(sun_vis)

        # ── moon pre-glow at horizon (scaled by cloud occlusion)
        if 0 <= m_el <= 15:
            illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
            if illumination > 0.10:
                horiz_pos = sky_to_screen(0.1, m_az, W, H)
                if horiz_pos:
                    hx = horiz_pos[0]; hy = H * 0.72
                    pg_intens = _clamp(1.0 - m_el / 15.0, 0.0, 1.0) * illumination * moon_vis
                    pgr = W * 0.35
                    pg = cairo.RadialGradient(hx, hy, 0, hx, hy, pgr)
                    pg.add_color_stop_rgba(0.00, 0.90, 0.90, 0.82, pg_intens * 0.38)
                    pg.add_color_stop_rgba(0.28, 0.76, 0.76, 0.68, pg_intens * 0.16)
                    pg.add_color_stop_rgba(0.60, 0.55, 0.55, 0.48, pg_intens * 0.05)
                    pg.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
                    cr.arc(hx, hy, pgr, 0, 2 * math.pi)
                    cr.set_source(pg)
                    cr.fill()

        # ── moon (show only when above horizon)
        if m_el > 0:
            pos = sky_to_screen(m_el, m_az, W, H)
            if pos:
                sun_rel    = ((sun_az - _FACING + 180.0) % 360.0) - 180.0
                sun_t      = _clamp((sun_rel + 120.0) / 240.0, 0.0, 1.0)
                sun_sx     = W * 0.06 + sun_t * (W * 0.88)
                sun_sy     = H * 0.72 - (H * 0.66) * (sun_el / 90.0)
                limb_angle = math.atan2(pos[1] - sun_sy, sun_sx - pos[0])
                self._moon_limb_angle = limb_angle
                use_group  = moon_vis < 0.999
                if use_group:
                    cr.push_group()
                self._draw_moon(cr, pos[0], pos[1], phase, scale, limb_angle)
                if use_group:
                    cr.pop_group_to_source()
                    cr.paint_with_alpha(moon_vis)

        # ── planets (fully hidden behind thick cloud)
        if sky_vis > 0.02:
            planets = planet_positions(lat, lon, utc)
            if sky_vis < 0.999:
                cr.push_group()
            self._draw_planets(cr, W, H, planets, scale)
            if sky_vis < 0.999:
                cr.pop_group_to_source()
                cr.paint_with_alpha(sky_vis)

        # Constellation names only meaningful at night
        if sun_el >= -5:
            self._hover_const = None
            self._star_screen_cache = {}

        # ── HUD cards (astronomical info — off by default, toggle in Settings)
        if not clean and cfg.get('show_info_cards', False):
            self._draw_cards(cr, W, H, now, sun_el, phase, age, m_el)

        # ── Weekly forecast column (accordion — hourly expands under clicked day)
        if not clean and cfg.get('show_weekly_forecast', True):
            self._draw_weekly_forecast(cr, W, H)

        # ── Horizon direction labels
        if cfg.get('show_horizon_labels', True):
            self._draw_horizon_labels(cr, W, H)

        # ── Compass rose (top-left, toggleable)
        if cfg.get('show_compass', True):
            self._draw_compass(cr, 62, 95, 46)

        # ── Gear / settings button
        self._draw_gear_btn(cr, gx, gy, 16)

        # ── Constellation hover label
        if (self._hover_const
                and self.cfg.get('show_constellations', True)
                and 0 < self._mouse_x < W
                and 0 < self._mouse_y < H):
            self._draw_const_label(cr, self._mouse_x, self._mouse_y,
                                   self._hover_const, W, H)

    # ── Sky background ───────────────────────────────────────────────────────

    def _draw_sky(self, cr, W, H, sun_el, sun_az, m_el, m_az, clouds, m_bright,
                  lat=6.14, lon=1.21, utc=None):
        r, g, b, a = sky_color_adaptive(sun_el, clouds, m_bright)
        grad = cairo.LinearGradient(0, 0, 0, H)
        # At night keep the bottom dark too — prevents bright wallpaper bleeding through
        night = sun_el < -6
        a_mid = a * 0.88 if night else a * 0.75
        a_bot = a * 0.70 if night else a * 0.35
        grad.add_color_stop_rgba(0.0, min(1, r * 1.15), min(1, g * 1.15), min(1, b * 1.15), a)
        grad.add_color_stop_rgba(0.6, r,        g,        b,        a_mid)
        grad.add_color_stop_rgba(1.0, r * 0.70, g * 0.70, b * 0.70, a_bot)
        cr.set_source(grad)
        cr.paint()

        self._draw_horizon_effects(cr, W, H, sun_el, sun_az)

        if sun_el < -5:
            star_vis = 1.0 - _clamp((clouds['total'] - 20) / 65.0, 0.0, 1.0)
            self._draw_stars(cr, W, H,
                             _clamp((-5 - sun_el) / 13, 0, 1) * star_vis,
                             lat, lon, utc, m_bright)
            self._maybe_spawn_meteor(W, H)
            self._draw_meteors(cr, W, H)

        if clouds['total'] > 0:
            body_pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H) if sun_el > -0.83 else None
            if body_pos is None and m_el > 0:
                body_pos = sky_to_screen(m_el, m_az, W, H)
            self._draw_clouds(cr, W, H, clouds, sun_el, body_pos)

        precip = clouds.get('precip', 0.0)
        if precip > 0:
            if self.cfg.get('show_rainbow', True):
                self._draw_rainbow(cr, W, H, sun_el, sun_az, precip)
            self._draw_rain(cr, W, H, precip, clouds.get('snow', False))

        # Silhouette last — always in front of sky, stars, and clouds
        if self.cfg.get('show_silhouette', True):
            self._draw_horizon_silhouette(cr, W, H)

    def _draw_horizon_effects(self, cr, W, H, sun_el, sun_az):
        """Layered horizon effects: Belt of Venus, pre-glow, golden-hour band, atmospheric haze."""
        y0 = H * 0.72

        # ── Belt of Venus: pink/mauve arch on the anti-solar horizon at twilight ──
        # Visible when sun is -1° to -10°, opposite the sunset/sunrise direction.
        if -10.0 < sun_el < -0.5:
            anti_az  = (sun_az + 180.0) % 360.0
            anti_rel = ((anti_az - _FACING + 180.0) % 360.0) - 180.0
            if abs(anti_rel) < 120.0:
                anti_t  = _clamp((anti_rel + 120.0) / 240.0, 0.0, 1.0)
                ax      = W * 0.06 + anti_t * (W * 0.88)
                intens  = _clamp(1.0 - abs(sun_el + 5.0) / 5.0, 0.0, 1.0) ** 1.4
                bv_r    = W * 0.58
                bv = cairo.RadialGradient(ax, y0, 0, ax, y0, bv_r)
                bv.add_color_stop_rgba(0.00, 0.88, 0.52, 0.72, intens * 0.42)
                bv.add_color_stop_rgba(0.18, 0.72, 0.38, 0.62, intens * 0.28)
                bv.add_color_stop_rgba(0.45, 0.45, 0.20, 0.48, intens * 0.12)
                bv.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
                cr.arc(ax, y0, bv_r, 0, 2 * math.pi)
                cr.set_source(bv)
                cr.fill()

        # ── Pre-glow: sun just below horizon (-12° to 0°) ────────────────────
        # Deep orange-red radial bloom centred on the sun's horizon point.
        if -12.0 < sun_el < 0.0:
            sun_rel = ((sun_az - _FACING + 180.0) % 360.0) - 180.0
            sun_t   = _clamp((sun_rel + 120.0) / 240.0, 0.0, 1.0)
            gx      = W * 0.06 + sun_t * (W * 0.88)
            intens  = _clamp(1.0 - abs(sun_el) / 12.0, 0.0, 1.0) ** 1.5
            gr      = W * 0.52
            grd = cairo.RadialGradient(gx, y0, 0, gx, y0, gr)
            grd.add_color_stop_rgba(0.00, 1.00, 0.45, 0.02, intens * 0.60)
            grd.add_color_stop_rgba(0.22, 1.00, 0.30, 0.01, intens * 0.32)
            grd.add_color_stop_rgba(0.55, 0.80, 0.15, 0.00, intens * 0.10)
            grd.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
            cr.arc(gx, y0, gr, 0, 2 * math.pi)
            cr.set_source(grd)
            cr.fill()

        # ── Golden-hour band: warm strip across the full horizon ──────────────
        # Peaks near sun_el ≈ 2°; fades out above 15° and below -6°.
        if -6.0 < sun_el < 15.0:
            intens = _clamp(1.0 - abs(sun_el - 2.0) / 8.0, 0.0, 1.0) ** 2.0
            if intens > 0.01:
                gh = H * 0.22
                grd = cairo.LinearGradient(0, y0 - gh, 0, y0)
                grd.add_color_stop_rgba(0.00, 0.00, 0.00, 0.00, 0.00)
                grd.add_color_stop_rgba(0.50, 1.00, 0.55, 0.06, intens * 0.10)
                grd.add_color_stop_rgba(0.78, 1.00, 0.38, 0.02, intens * 0.20)
                grd.add_color_stop_rgba(1.00, 1.00, 0.22, 0.01, intens * 0.16)
                cr.rectangle(0, y0 - gh, W, gh)
                cr.set_source(grd)
                cr.fill()

        # ── Atmospheric haze: subtle veil on the lower sky ────────────────────
        # Gives visual depth — daytime blue-white, nighttime dark haze.
        hz = H * 0.18
        if sun_el > 0:
            hr, hg, hb, ha = 0.82, 0.88, 1.00, 0.09
        else:
            hr, hg, hb, ha = 0.06, 0.07, 0.14, 0.06
        hrd = cairo.LinearGradient(0, y0 - hz, 0, y0)
        hrd.add_color_stop_rgba(0.0, hr, hg, hb, 0.00)
        hrd.add_color_stop_rgba(1.0, hr, hg, hb, ha)
        cr.rectangle(0, y0 - hz, W, hz)
        cr.set_source(hrd)
        cr.fill()

    def _draw_stars(self, cr, W, H, intensity, lat=6.14, lon=1.21, utc=None, m_bright=0.0):
        if utc is None:
            utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        rng = random.Random(42)

        # ── Background faint star field — static texture of dim (mag 5-7) stars ──
        rng_bg = random.Random(0xC7D9)
        bg_limit = intensity * (1.0 - m_bright * 0.88)
        for _ in range(420):
            bsx = rng_bg.uniform(0, W)
            bsy = rng_bg.uniform(0, H * 0.72)
            ba  = bg_limit * rng_bg.uniform(0.03, 0.16)
            if ba < 0.015:
                rng_bg.random()   # keep rng state stable
                continue
            br = rng_bg.uniform(0.3, 0.65)
            cr.set_source_rgba(0.88, 0.90, 0.96, ba)
            cr.arc(bsx, bsy, br, 0, 2 * math.pi)
            cr.fill()

        # ── Airglow — faint green emission band near horizon on dark nights ──────
        if intensity > 0.4 and m_bright < 0.80:
            ag_a = (intensity - 0.4) / 0.6 * 0.036 * (1.0 - m_bright / 0.80)
            ag_grd = cairo.LinearGradient(0, H * 0.57, 0, H * 0.72)
            ag_grd.add_color_stop_rgba(0.0, 0.00, 0.00, 0.00, 0.00)
            ag_grd.add_color_stop_rgba(1.0, 0.28, 0.65, 0.30, ag_a)
            cr.rectangle(0, H * 0.57, W, H * 0.15)
            cr.set_source(ag_grd)
            cr.fill()

        # ── Milky Way — fades under moonlight (bright moon washes it out)
        if intensity > 0.5 and m_bright < 0.7:
            mw_alpha = (intensity - 0.5) * 2 * 0.07 * (1.0 - m_bright / 0.7)
            pdx, pdy = 1.2 * W, -0.45 * H
            plen = math.sqrt(pdx * pdx + pdy * pdy)
            nx, ny = -pdy / plen, pdx / plen
            for i in range(180):
                t      = i / 179.0
                cx     = W * (-0.1 + t * 1.2)
                cy     = H * (0.55 - t * 0.45)
                spread = rng.gauss(0, H * 0.09)
                bx     = cx + nx * spread + rng.uniform(-W * 0.01, W * 0.01)
                by     = cy + ny * spread + rng.uniform(-H * 0.01, H * 0.01)
                bw     = W * rng.uniform(0.05, 0.14)
                bh     = H * rng.uniform(0.05, 0.13)
                a      = mw_alpha * rng.uniform(0.3, 1.0)
                _soft_puff(cr, bx, by, bw, bh, 0.60, 0.65, 0.80, a)

        # ── Real star catalog — positions computed from RA/Dec for current time
        # Moon washes out dim stars: full moon → limiting mag ~3.0; no moon → ~6.5
        limiting_mag = 6.5 - m_bright * 3.5

        star_data = _get_star_positions(lat, lon, utc)

        # Build screen-position lookup keyed by rounded RA/Dec for constellation lines
        star_screen = {}
        for alt, az, mag, bv, ra_h, dec_deg in star_data:
            pos = sky_to_screen(alt, az, W, H)
            if pos is not None:
                star_screen[(round(ra_h, 2), round(dec_deg, 1))] = pos
        self._star_screen_cache = star_screen

        # Constellation lines drawn before stars so stars render on top
        if self.cfg.get('show_constellations', True):
            line_alpha = 0.28 * intensity * max(0.0, 1.0 - m_bright * 0.8)
            if line_alpha > 0.01:
                cr.set_line_width(0.8)
                for name, polylines in _CONSTELLATIONS:
                    hovered = (name == self._hover_const)
                    if hovered:
                        cr.set_source_rgba(0.75, 0.85, 1.00, min(1.0, line_alpha * 2.8))
                    else:
                        cr.set_source_rgba(0.55, 0.65, 0.95, line_alpha)
                    for polyline in polylines:
                        prev = None
                        for ra_h_pt, dec_deg_pt in polyline:
                            key = (round(ra_h_pt, 2), round(dec_deg_pt, 1))
                            pt = star_screen.get(key)
                            if pt is None:
                                prev = None
                                continue
                            if prev is not None:
                                cr.move_to(prev[0], prev[1])
                                cr.line_to(pt[0], pt[1])
                                cr.stroke()
                            prev = pt

        for alt, az, mag, bv, ra_h, dec_deg in star_data:
            pos = star_screen.get((round(ra_h, 2), round(dec_deg, 1)))
            if pos is None:
                continue
            sx, sy = pos
            sr, sg, sb = _bv_to_rgb(bv)

            moon_fade = _clamp((limiting_mag - mag) / 2.0, 0.0, 1.0)
            if moon_fade <= 0:
                continue

            elev_fade = _clamp((alt + 1.0) / 12.0, 0.0, 1.0)
            alpha     = intensity * elev_fade * moon_fade * _clamp((6.0 - mag) / 6.5, 0.05, 1.0)
            if utc is not None:
                t_sec     = utc.hour * 3600 + utc.minute * 60 + utc.second
                phase_off = (ra_h * 7919.0 + abs(dec_deg) * 3571.0) % (2 * math.pi)
                alpha     = _clamp(alpha * (1.0 + 0.14 * math.sin(t_sec * 2.7 + phase_off)), 0.0, 1.0)
            radius    = max(0.4, (5.5 - mag) * 0.38)

            cr.set_source_rgba(sr, sg, sb, alpha)
            cr.arc(sx, sy, radius, 0, 2 * math.pi)
            cr.fill()

            if mag < 2.0:
                glow_r = radius * 3.5 + 1.5
                _soft_puff(cr, sx, sy, glow_r, glow_r,
                           sr, sg, sb, alpha * 0.35 * intensity)

        # ── Orion Nebula (M42) — faint pink-teal glow below Orion's belt ────────
        m42_alt, m42_az = _ra_dec_to_alt_az(5.5875, -5.391, lat, lon, utc)
        if m42_alt > 0:
            m42_pos = sky_to_screen(m42_alt, m42_az, W, H)
            if m42_pos:
                nf = intensity * _clamp((m42_alt + 1.0) / 18.0, 0.0, 1.0) * (1.0 - m_bright * 0.75)
                if nf > 0.01:
                    nx, ny = m42_pos
                    nw, nh = W * 0.013, H * 0.020
                    _soft_puff(cr, nx, ny, nw, nh, 0.85, 0.55, 0.72, nf * 0.38)
                    _soft_puff(cr, nx, ny, nw * 0.55, nh * 0.55, 0.50, 0.72, 0.80, nf * 0.28)

    # ── Crepuscular rays ─────────────────────────────────────────────────────

    def _draw_crepuscular_rays(self, cr, W, H, sun_el, sun_az, scale):
        if sun_el < -1 or sun_el > 28:
            return
        pos = sky_to_screen(max(sun_el, 0.5), sun_az, W, H)
        if pos is None:
            return
        sx, sy   = pos
        intens   = _clamp(1.0 - abs(sun_el - 6.0) / 18.0, 0.0, 1.0) ** 2.0
        if intens < 0.01:
            return
        n_rays   = 7
        ray_len  = W * 1.3
        half_w   = W * 0.006
        rng      = random.Random(datetime.date.today().toordinal())
        cr.save()
        cr.set_operator(cairo.Operator.SCREEN)
        for _ in range(n_rays):
            ang  = rng.uniform(0, 2 * math.pi)
            alph = rng.uniform(0.012, 0.040) * intens
            ex   = sx + ray_len * math.cos(ang)
            ey   = sy + ray_len * math.sin(ang)
            nx   = -math.sin(ang) * half_w
            ny   =  math.cos(ang) * half_w
            cr.new_path()
            cr.move_to(sx + nx, sy + ny)
            cr.line_to(sx - nx, sy - ny)
            cr.line_to(ex,      ey)
            cr.close_path()
            grd = cairo.LinearGradient(sx, sy, ex, ey)
            grd.add_color_stop_rgba(0.00, 1.0, 0.98, 0.82, alph * 2.0)
            grd.add_color_stop_rgba(0.25, 1.0, 0.95, 0.72, alph)
            grd.add_color_stop_rgba(1.00, 1.0, 0.90, 0.60, 0.00)
            cr.set_source(grd)
            cr.fill()
        cr.restore()

    # ── Lunar halo ───────────────────────────────────────────────────────────

    def _draw_lunar_halo(self, cr, x, y, moon_r, clouds, phase):
        if clouds.get('high', 0) < 20:
            return
        illumination = (1 - math.cos(phase * 2 * math.pi)) / 2
        if illumination < 0.20:
            return
        intens  = min(clouds['high'] / 100.0, 1.0) * illumination
        halo_r  = moon_r * 5.2   # 22° halo ≈ 5× moon radius on screen
        inner_r = halo_r * 0.88
        outer_r = halo_r * 1.12
        halo = cairo.RadialGradient(x, y, inner_r, x, y, outer_r)
        halo.add_color_stop_rgba(0.00, 0.00, 0.00, 0.00, 0.00)
        halo.add_color_stop_rgba(0.35, 0.90, 0.92, 0.95, intens * 0.20)
        halo.add_color_stop_rgba(0.50, 0.95, 0.96, 1.00, intens * 0.32)
        halo.add_color_stop_rgba(0.65, 0.90, 0.92, 0.95, intens * 0.20)
        halo.add_color_stop_rgba(1.00, 0.00, 0.00, 0.00, 0.00)
        cr.arc(x, y, outer_r, 0, 2 * math.pi)
        cr.set_source(halo)
        cr.fill()

    # ── Horizon direction labels ─────────────────────────────────────────────

    def _draw_horizon_labels(self, cr, W, H):
        y0 = H * 0.72
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(10)
        for lbl, az in [('N', 0), ('NE', 45), ('E', 90), ('SE', 135),
                        ('S', 180), ('SW', 225), ('W', 270), ('NW', 315)]:
            rel = ((az - _FACING + 180.0) % 360.0) - 180.0
            if abs(rel) > 117:
                continue
            t  = _clamp((rel + 120.0) / 240.0, 0.0, 1.0)
            lx = W * 0.06 + t * (W * 0.88)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.22)
            cr.set_line_width(1.0)
            cr.move_to(lx, y0 - 5)
            cr.line_to(lx, y0 + 5)
            cr.stroke()
            ext = cr.text_extents(lbl)
            col = (1.0, 0.30, 0.30, 0.72) if lbl == 'N' else (0.85, 0.90, 1.00, 0.42)
            cr.set_source_rgba(*col)
            cr.move_to(lx - ext.width / 2 - ext.x_bearing, y0 - 9)
            cr.show_text(lbl)

    # ── Rainbow ──────────────────────────────────────────────────────────────

    def _draw_rainbow(self, cr, W, H, sun_el, sun_az, precip):
        if precip < 0.1 or sun_el < 10 or sun_el > 45:
            return
        anti_az  = (sun_az + 180.0) % 360.0
        anti_rel = ((anti_az - _FACING + 180.0) % 360.0) - 180.0
        if abs(anti_rel) > 118.0:
            return
        anti_t  = _clamp((anti_rel + 120.0) / 240.0, 0.0, 1.0)
        ax      = W * 0.06 + anti_t * (W * 0.88)
        y0      = H * 0.72
        top_el  = 42.0 - sun_el
        if top_el <= 0:
            return
        top_y   = H * 0.72 - (H * 0.66) * _clamp(top_el / 90.0, 0, 1)
        bow_r   = y0 - top_y
        if bow_r < 10:
            return
        intens  = min(precip / 5.0, 1.0) * _clamp((45.0 - sun_el) / 35.0, 0, 1)
        bow_w   = bow_r * 0.028
        cr.save()
        cr.set_line_width(bow_w)
        for i, (r, g, b) in enumerate([
                (1.00, 0.10, 0.00),   # red outer
                (1.00, 0.50, 0.00),   # orange
                (1.00, 0.95, 0.00),   # yellow
                (0.15, 0.85, 0.15),   # green
                (0.10, 0.30, 1.00),   # blue
                (0.38, 0.00, 0.90),   # violet inner
        ]):
            ri = bow_r * (1.0 + (2 - i) * 0.018)
            cr.arc(ax, y0, ri, math.pi, 0)
            cr.set_source_rgba(r, g, b, intens * 0.18)
            cr.stroke()
        cr.restore()

    # ── Lock-screen export ───────────────────────────────────────────────────

    def _render_frame_to_surface(self):
        """Render the current sky frame off-screen and return an ImageSurface."""
        alloc = self.da.get_allocation()
        W, H  = alloc.width, alloc.height
        if W < 10 or H < 10:
            return None
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr   = cairo.Context(surf)
        # Black background so the sky renders correctly as a wallpaper
        cr.set_source_rgb(0.0, 0.0, 0.0)
        cr.paint()
        self._on_draw(self.da, cr)
        return surf

    def _export_lockscreen_bg(self):
        """Save current sky frame as PNG and push it to background/lock screen per config."""
        mode = self.cfg.get('lockscreen_export', 'off')
        if mode == 'off':
            return True   # keep timer alive
        # Render on the main thread (GTK/Cairo requirement), then hand PNG bytes to a thread
        surf = self._render_frame_to_surface()
        if surf is None:
            return True
        out_dir  = os.path.expanduser('~/.cache')
        out_path = os.path.join(out_dir, 'caelum-lockscreen.png')
        def _work(surface, path, export_mode):
            try:
                os.makedirs(out_dir, exist_ok=True)
                surface.write_to_png(path)
                uri = f'file://{path}'
                if export_mode in ('background', 'both'):
                    subprocess.run(['gsettings', 'set',
                                    'org.gnome.desktop.background',
                                    'picture-uri', uri], check=False)
                    subprocess.run(['gsettings', 'set',
                                    'org.gnome.desktop.background',
                                    'picture-uri-dark', uri], check=False)
                if export_mode in ('lockscreen', 'both'):
                    subprocess.run(['gsettings', 'set',
                                    'org.gnome.desktop.screensaver',
                                    'picture-uri', uri], check=False)
            except Exception:
                pass
        threading.Thread(target=_work, args=(surf, out_path, mode), daemon=True).start()
        return True   # keep timer alive

    def _draw_gear_btn(self, cr, cx, cy, r, off=False):
        if off:
            bg   = (0.28, 0.04, 0.04, 0.72)
            ring = (1.0, 0.35, 0.35, 0.50)
            icon = (1.0, 0.55, 0.55, 0.95)
            hole = (0.28, 0.04, 0.04, 0.72)
        else:
            bg   = (0.04, 0.05, 0.12, 0.58)
            ring = (1.0,  1.0,  1.0,  0.22)
            icon = (1.0,  1.0,  1.0,  0.88)
            hole = (0.04, 0.05, 0.12, 0.58)

        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*bg)
        cr.fill()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(*ring)
        cr.set_line_width(1)
        cr.stroke()

        cr.save()
        cr.translate(cx, cy)
        cr.set_source_rgba(*icon)
        n = 8
        ro, ri = r * 0.66, r * 0.44
        tooth = math.pi / n * 0.55
        cr.new_path()
        for i in range(n):
            mid = 2 * math.pi * i / n
            a0, a1 = mid - math.pi / n + tooth, mid - tooth
            a2, a3 = mid + tooth, mid + math.pi / n - tooth
            cr.arc(0, 0, ri, a0 - 0.01, a0)
            cr.arc(0, 0, ro, a1, a2)
            cr.arc(0, 0, ri, a3, a3 + 0.01)
        cr.close_path()
        cr.fill()
        cr.set_source_rgba(*hole)
        cr.arc(0, 0, r * 0.22, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    def _draw_const_label(self, cr, mx, my, name, W, H):
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(13)
        ext = cr.text_extents(name)
        pw, ph = ext.width + 20, 26
        px = _clamp(mx + 16, 4, W - pw - 4)
        py = _clamp(my - ph - 8, 4, H - ph - 4)
        self._rrect(cr, px, py, pw, ph, 6)
        cr.set_source_rgba(0.04, 0.05, 0.14, 0.72)
        cr.fill_preserve()
        cr.set_source_rgba(0.55, 0.65, 0.95, 0.45)
        cr.set_line_width(1)
        cr.stroke()
        cr.set_source_rgba(0.85, 0.90, 1.00, 0.95)
        cr.move_to(px + 10, py + ph - 7)
        cr.show_text(name)

    def _draw_clouds(self, cr, W, H, clouds, sun_el, body_screen_pos=None):
        top_col, dark_col, cir_col = _cloud_palette(sun_el)
        today = datetime.date.today()
        hour  = datetime.datetime.now().hour
        rng_d = random.Random(today.toordinal())
        rng_h = random.Random(today.toordinal() * 24 + hour)

        # If total > 0 but no layer data, put it all in mid level
        high_cov = clouds['high']
        mid_cov  = clouds['mid']
        low_cov  = clouds['low']
        total    = clouds['total']
        wmo      = clouds.get('wmo', 0)
        if total > 0 and high_cov == 0 and mid_cov == 0 and low_cov == 0:
            mid_cov = total

        # Overcast sheet: uniform gray ceiling for heavily overcast skies
        if total > 65:
            _draw_overcast_sheet(cr, W, H, total, top_col, dark_col)

        # Back-to-front: cirrus → altocumulus → cumulus
        draw_cirrus(     cr, W, H, high_cov, cir_col,                    rng_d)
        draw_altocumulus(cr, W, H, mid_cov,  top_col,                    rng_h)
        draw_cumulus(    cr, W, H, low_cov,  top_col, dark_col, rng_h, wmo=wmo)

        # Celestial body glow: illuminates clouds around sun/moon position
        if body_screen_pos and clouds['total'] > 0:
            self._draw_body_glow_on_clouds(cr, W, H, body_screen_pos, sun_el)

    def _draw_body_glow_on_clouds(self, cr, W, H, pos, sun_el):
        """
        Radial light gradient from the sun or moon that brightens nearby clouds.
        At night this is cool silver-white (moonlight, no pollution).
        At sunrise/sunset it's warm gold.
        """
        bx, by = pos
        radius = W * 0.42   # glow spreads wide across the sky

        if sun_el < -0.83:  # moon is the source — natural silver
            col_inner = (0.92, 0.90, 0.82)
            col_mid   = (0.76, 0.74, 0.66)
            a_inner, a_mid = 0.55, 0.22
        elif sun_el < 8:    # golden hour / sunrise-sunset — warm gold
            col_inner = (1.00, 0.82, 0.45)
            col_mid   = (1.00, 0.65, 0.20)
            a_inner, a_mid = 0.42, 0.16
        else:               # daytime — bright white-blue
            col_inner = (1.00, 1.00, 1.00)
            col_mid   = (0.88, 0.92, 1.00)
            a_inner, a_mid = 0.28, 0.08

        grd = cairo.RadialGradient(bx, by, 0, bx, by, radius)
        grd.add_color_stop_rgba(0.00, col_inner[0], col_inner[1], col_inner[2], a_inner)
        grd.add_color_stop_rgba(0.35, col_mid[0],   col_mid[1],   col_mid[2],   a_mid)
        grd.add_color_stop_rgba(0.75, col_mid[0],   col_mid[1],   col_mid[2],   a_mid * 0.3)
        grd.add_color_stop_rgba(1.00, 0, 0, 0, 0)
        cr.rectangle(0, 0, W, H)
        cr.set_source(grd)
        cr.fill()

    # ── Planets ──────────────────────────────────────────────────────────────

    def _draw_planets(self, cr, W, H, planets, scale):
        for name, el, az, col in planets:
            if el <= 0:
                continue
            pos = sky_to_screen(el, az, W, H)
            if pos is None:
                continue
            px, py = pos
            r, g, b = col
            mag    = _PLANET_MAG.get(name, 0.0)
            radius = max(3.5, (5.5 - mag * 0.50)) * scale
            glow = cairo.RadialGradient(px, py, 0, px, py, radius * 3.5)
            glow.add_color_stop_rgba(0.0, r, g, b, 0.60)
            glow.add_color_stop_rgba(0.5, r, g, b, 0.22)
            glow.add_color_stop_rgba(1.0, r, g, b, 0.00)
            cr.arc(px, py, radius * 3.5, 0, 2 * math.pi)
            cr.set_source(glow)
            cr.fill()
            cr.set_source_rgba(r, g, b, 0.95)
            cr.arc(px, py, radius, 0, 2 * math.pi)
            cr.fill()
            if name == 'Saturn':
                cr.save()
                cr.translate(px, py)
                cr.scale(1.0, 0.32)
                cr.set_source_rgba(r, g, b, 0.50)
                cr.set_line_width(radius * 0.55)
                cr.arc(0, 0, radius * 2.1, 0, 2 * math.pi)
                cr.stroke()
                cr.restore()
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgba(r, g, b, 0.72)
            cr.move_to(px + radius + 3, py + 4)
            cr.show_text(name)

    # ── Compass rose ─────────────────────────────────────────────────────────

    def _draw_compass(self, cr, cx, cy, r):
        pi2      = 2 * math.pi
        # heading = real device heading when hw compass is active, else manual facing
        heading  = (float(self._hw_heading)
                    if self._hw_heading is not None
                    else float(self.cfg.get('facing', 180.0)))
        fac_ang  = math.radians(heading) - math.pi / 2   # screen angle, N=up=−pi/2
        half_fov = math.radians(120)                      # 240° total FOV

        # Background disc
        cr.arc(cx, cy, r, 0, pi2)
        cr.set_source_rgba(0.04, 0.06, 0.14, 0.62)
        cr.fill()
        cr.arc(cx, cy, r, 0, pi2)
        cr.set_source_rgba(1, 1, 1, 0.20)
        cr.set_line_width(1)
        cr.stroke()

        # Field-of-view wedge: 240° sector showing panorama coverage
        cr.move_to(cx, cy)
        cr.arc(cx, cy, r * 0.50, fac_ang - half_fov, fac_ang + half_fov)
        cr.close_path()
        cr.set_source_rgba(0.50, 0.72, 1.0, 0.13)
        cr.fill()
        # Facing direction arrow
        cr.move_to(cx, cy)
        cr.line_to(cx + r * 0.42 * math.cos(fac_ang),
                   cy + r * 0.42 * math.sin(fac_ang))
        cr.set_source_rgba(0.50, 0.72, 1.0, 0.55)
        cr.set_line_width(1.5)
        cr.stroke()

        # Tick marks — 8 directions (4 cardinal + 4 intercardinal)
        for i in range(8):
            ang   = pi2 * i / 8 - math.pi / 2   # 0 = North = up
            major = (i % 2 == 0)
            r_in  = r * (0.72 if major else 0.82)
            r_out = r * 0.94
            cr.move_to(cx + r_in  * math.cos(ang), cy + r_in  * math.sin(ang))
            cr.line_to(cx + r_out * math.cos(ang), cy + r_out * math.sin(ang))
            cr.set_source_rgba(1, 1, 1, 0.55 if major else 0.28)
            cr.set_line_width(1.2 if major else 0.7)
            cr.stroke()

        # N / E / S / W labels
        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        cr.set_font_size(r * 0.30)
        for lbl, frac in [('N', 0), ('E', 0.25), ('S', 0.5), ('W', 0.75)]:
            ang  = pi2 * frac - math.pi / 2
            lx   = cx + r * 0.52 * math.cos(ang)
            ly   = cy + r * 0.52 * math.sin(ang)
            ext  = cr.text_extents(lbl)
            col  = (1.0, 0.30, 0.30, 0.95) if lbl == 'N' else (0.90, 0.92, 1.0, 0.80)
            cr.set_source_rgba(*col)
            cr.move_to(lx - ext.width / 2 - ext.x_bearing,
                       ly - ext.height / 2 - ext.y_bearing)
            cr.show_text(lbl)

        # Needle — diamond; rotate so red tip always points geographic North.
        # When heading=0 (facing N): no rotation, red tip at top.
        # When heading=90 (facing E): rotate -90 deg, red tip points left.
        nl = r * 0.52   # north arm length
        sl = r * 0.34   # south arm length
        nw = r * 0.12   # half-width at pivot

        cr.save()
        cr.translate(cx, cy)
        cr.rotate(-math.radians(heading))   # needle tracks geographic North

        # North half (red)
        cr.new_path()
        cr.move_to(0, -nl)
        cr.line_to(-nw, 0)
        cr.line_to( nw, 0)
        cr.close_path()
        cr.set_source_rgba(0.95, 0.22, 0.22, 0.92)
        cr.fill()

        # South half (white/silver)
        cr.new_path()
        cr.move_to(0,  sl)
        cr.line_to(-nw, 0)
        cr.line_to( nw, 0)
        cr.close_path()
        cr.set_source_rgba(0.88, 0.90, 0.95, 0.80)
        cr.fill()

        cr.restore()

        # Pivot dot (drawn after restore, no rotation needed)
        cr.arc(cx, cy, r * 0.09, 0, pi2)
        cr.set_source_rgba(0.10, 0.12, 0.18, 0.95)
        cr.fill()
        cr.arc(cx, cy, r * 0.09, 0, pi2)
        cr.set_source_rgba(1, 1, 1, 0.40)
        cr.set_line_width(0.8)
        cr.stroke()

        # Hover highlight ring — shown in manual mode when mouse is over compass
        if (self._hw_heading is None
                and getattr(self, '_hover_compass', False)):
            cr.arc(cx, cy, r + 2, 0, pi2)
            cr.set_source_rgba(0.50, 0.80, 1.0, 0.55)
            cr.set_line_width(2.0)
            cr.stroke()
            # Small "click to set facing" label below compass
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgba(0.70, 0.88, 1.0, 0.80)
            lbl = 'click to set facing'
            ext = cr.text_extents(lbl)
            cr.move_to(cx - ext.width / 2, cy + r + 14)
            cr.show_text(lbl)

    # ── Horizon silhouette ───────────────────────────────────────────────────

    def _draw_horizon_silhouette(self, cr, W, H):
        rng  = random.Random(0xA5B2)
        y0   = H * 0.72
        # Build list of (x_peak, y_peak, seg_width) peaks
        peaks = []
        x = 0.0
        while x < W + W * 0.05:
            seg   = rng.uniform(W * 0.014, W * 0.048)
            shape = rng.random()
            if shape < 0.25:
                ht = rng.uniform(H * 0.06, H * 0.13)
            elif shape < 0.55:
                ht = rng.uniform(H * 0.02, H * 0.055)
            else:
                ht = rng.uniform(0.0, H * 0.018)
            peaks.append((x + seg * 0.5, y0 - ht, seg))
            x += seg

        cr.new_path()
        cr.move_to(0, H)
        cr.line_to(0, y0)

        for i, (px, py, sw) in enumerate(peaks):
            if i == 0:
                cr.curve_to(px - sw * 0.40, y0, px - sw * 0.15, py, px, py)
            else:
                ppx, ppy, psw = peaks[i - 1]
                mid_x = (ppx + px) / 2.0
                cr.curve_to(ppx + psw * 0.30, ppy, mid_x - sw * 0.12, y0, mid_x, y0)
                cr.curve_to(mid_x + sw * 0.12, y0, px - sw * 0.20,   py, px,     py)

        if peaks:
            lpx, _, lsw = peaks[-1]
            cr.curve_to(lpx + lsw * 0.30, y0, W, y0, W, y0)

        cr.line_to(W, H)
        cr.close_path()
        cr.set_source_rgba(0.04, 0.07, 0.04, 0.72)
        cr.fill()

    # ── Shooting stars ───────────────────────────────────────────────────────

    def _maybe_spawn_meteor(self, W, H):
        if random.random() > 0.006:
            return
        now = time.time()
        rng = random.Random(int(now * 1000))
        sx  = rng.uniform(0.05 * W, 0.92 * W)
        sy  = rng.uniform(0.03 * H, 0.42 * H)
        ang = rng.uniform(math.pi * 0.25, math.pi * 0.75)
        spd = rng.uniform(W * 0.20, W * 0.52)
        dur = rng.uniform(0.5, 1.4)
        lng = rng.uniform(W * 0.04, W * 0.11)
        self._meteors.append({
            'sx': sx, 'sy': sy, 'ang': ang, 'spd': spd,
            'start': now, 'dur': dur, 'lng': lng,
        })

    def _draw_meteors(self, cr, W, H):
        now   = time.time()
        still = []
        for m in self._meteors:
            t = (now - m['start']) / m['dur']
            if t >= 1.0:
                continue
            fade = math.sin(t * math.pi)
            dist = m['spd'] * m['dur'] * t
            ex   = m['sx'] + math.cos(m['ang']) * dist
            ey   = m['sy'] + math.sin(m['ang']) * dist
            bx   = ex - math.cos(m['ang']) * m['lng']
            by   = ey - math.sin(m['ang']) * m['lng']
            grad = cairo.LinearGradient(bx, by, ex, ey)
            grad.add_color_stop_rgba(0.00, 1.00, 0.50, 0.15, 0.00)          # orange tail fades
            grad.add_color_stop_rgba(0.35, 1.00, 0.78, 0.42, fade * 0.38)   # warm yellow
            grad.add_color_stop_rgba(0.70, 0.55, 0.95, 0.68, fade * 0.80)   # green-teal
            grad.add_color_stop_rgba(1.00, 0.88, 0.98, 0.92, fade * 1.00)   # white-green head
            cr.move_to(bx, by)
            cr.line_to(ex, ey)
            cr.set_source(grad)
            cr.set_line_width(1.5)
            cr.stroke()
            still.append(m)
        self._meteors = still

    # ── Rain / Snow ──────────────────────────────────────────────────────────

    def _draw_rain(self, cr, W, H, precip, snow):
        # Logarithmic scale so light drizzle (0.2mm) is already clearly visible
        intensity = min(math.log1p(precip) / math.log1p(20.0), 1.0)
        n         = int(intensity * 180) + 40
        t_seed    = int(time.time() * 8)
        rng       = random.Random(t_seed)
        if snow:
            cr.set_line_width(0)
            for _ in range(n):
                sx = rng.uniform(0, W)
                sy = rng.uniform(0, H * 0.92)
                cr.set_source_rgba(0.95, 0.97, 1.0, rng.uniform(0.35, 0.65))
                cr.arc(sx, sy, rng.uniform(1.5, 3.0), 0, 2 * math.pi)
                cr.fill()
        else:
            # Tilt streaks in the real wind direction from weather data
            wind_spd = self._clouds.get('wind_speed', 0.0)
            wind_frm = self._clouds.get('wind_dir',   180.0)
            wind_to  = (wind_frm + 180.0) % 360.0
            # Map wind_to azimuth to screen-space horizontal offset
            # rel: positive = right of panorama centre, negative = left
            rel_to   = ((wind_to - _FACING + 180.0) % 360.0) - 180.0
            tilt_x   = rel_to / 120.0 * min(wind_spd, 15.0) * 0.9
            dy       = 14.0
            dx       = _clamp(tilt_x, -12.0, 12.0)
            cr.set_line_width(1.0)
            # Alpha is independent of intensity — drop count already encodes how heavy the rain is
            for _ in range(n):
                sx = rng.uniform(0, W)
                sy = rng.uniform(0, H * 0.92)
                cr.set_source_rgba(0.70, 0.80, 1.0, rng.uniform(0.20, 0.38))
                cr.move_to(sx, sy)
                cr.line_to(sx + dx, sy + dy)
                cr.stroke()
            # Lightning — occasional full-screen flash during heavy rain
            if precip > 4.0 and random.random() < 0.004:
                cr.set_source_rgba(1.0, 1.0, 1.0, random.uniform(0.06, 0.20))
                cr.paint()

    # ── Sun ──────────────────────────────────────────────────────────────────

    def _draw_sun(self, cr, x, y, el, scale):
        # Real naked-eye sun: no visible disc, just a blinding bloom of light.
        # Three nested SCREEN-blended layers create the overexposed appearance.
        r = 16 * scale
        t = _clamp(el / 20.0, 0.0, 1.0)   # 0=horizon, 1=high sun

        cr.save()
        cr.set_operator(cairo.Operator.SCREEN)

        # Layer 1 — wide atmospheric diffusion (brightens a large sky area)
        wr = r * 16
        w = cairo.RadialGradient(x, y, 0, x, y, wr)
        w.add_color_stop_rgba(0.00, 1.0, 0.80 + 0.18*t, 0.30 + 0.55*t, 0.50)
        w.add_color_stop_rgba(0.18, 1.0, 0.65 + 0.15*t, 0.18 + 0.25*t, 0.18)
        w.add_color_stop_rgba(0.45, 1.0, 0.50,           0.10,           0.05)
        w.add_color_stop_rgba(1.00, 0.0, 0.0,            0.0,            0.00)
        cr.arc(x, y, wr, 0, 2 * math.pi)
        cr.set_source(w)
        cr.fill()

        # Layer 2 — bright bloom (main visible glare)
        br = r * 5
        b = cairo.RadialGradient(x, y, 0, x, y, br)
        b.add_color_stop_rgba(0.00, 1.0, 1.0,            0.88 + 0.12*t, 0.92)
        b.add_color_stop_rgba(0.25, 1.0, 0.90 + 0.10*t, 0.55 + 0.35*t, 0.75)
        b.add_color_stop_rgba(0.65, 1.0, 0.70,           0.28,           0.28)
        b.add_color_stop_rgba(1.00, 0.0, 0.0,            0.0,            0.00)
        cr.arc(x, y, br, 0, 2 * math.pi)
        cr.set_source(b)
        cr.fill()

        # Layer 3 — overexposed white-hot core (pure white, fully blown out)
        cr_r = r * 1.2
        c = cairo.RadialGradient(x, y, 0, x, y, cr_r)
        c.add_color_stop_rgba(0.00, 1.0, 1.0, 1.0, 1.00)
        c.add_color_stop_rgba(0.50, 1.0, 1.0, 0.95, 0.90)
        c.add_color_stop_rgba(1.00, 1.0, 0.90, 0.60, 0.00)
        cr.arc(x, y, cr_r, 0, 2 * math.pi)
        cr.set_source(c)
        cr.fill()

        cr.restore()

    # ── Moon ─────────────────────────────────────────────────────────────────

    def _draw_moon(self, cr, x, y, phase, scale, limb_angle=0.0):
        r = 32 * scale
        self._draw_lunar_halo(cr, x, y, r, self._clouds, phase)

        # Glow — unrotated, centered on screen pos
        glow = cairo.RadialGradient(x, y, r * 0.4, x, y, r * 3.5)
        glow.add_color_stop_rgba(0.0, 0.92, 0.91, 0.84, 0.55)
        glow.add_color_stop_rgba(0.4, 0.78, 0.76, 0.68, 0.18)
        glow.add_color_stop_rgba(1.0, 0.55, 0.53, 0.46, 0.00)
        cr.arc(x, y, r * 3.5, 0, 2 * math.pi)
        cr.set_source(glow)
        cr.fill()

        # Disc in local coords, rotated so lit side faces the sun
        # limb_angle: direction from moon toward sun in world (y-up) coords
        # canonical: lit side on +x (right); cr.rotate(-limb_angle) orients it correctly
        cr.save()
        cr.translate(x, y)
        cr.rotate(-limb_angle)

        cr.arc(0, 0, r, 0, 2 * math.pi)
        cr.clip()
        cr.set_source_rgba(0.16, 0.20, 0.45, 0.03)
        cr.paint()

        t = math.cos(phase * 2 * math.pi)
        cr.set_source_rgba(0.96, 0.94, 0.86, 1.0)
        if t < -0.95:
            # Full moon: fill entire disc
            cr.arc(0, 0, r, 0, 2 * math.pi)
            cr.fill()
        else:
            # Waxing OR waning: always draw lit side on +x; limb_angle rotation handles direction
            cr.move_to(0, -r)
            cr.arc(0, 0, r, -math.pi / 2, math.pi / 2)
            cr.save()
            cr.scale(t, 1.0)
            cr.arc_negative(0, 0, r, math.pi / 2, -math.pi / 2)
            cr.restore()
            cr.close_path()
            cr.fill()
        cr.restore()

    # ── Weather icon (Cairo-drawn, no external files) ─────────────────────────

    def _draw_wx_icon(self, cr, cx, cy, size, sym):
        """Draw a weather icon centred at (cx, cy) fitting in size × size."""
        if not sym:
            return
        s = size * 0.5
        cr.save()

        # ── helpers ──────────────────────────────────────────────────────────

        def _sun(ox=0.0, oy=0.0, r=None, alpha=0.95):
            r = r if r is not None else s * 0.44
            cr.set_source_rgba(1.0, 0.88, 0.22, alpha)
            cr.arc(cx + ox, cy + oy, r * 0.48, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.88, 0.22, alpha * 0.70)
            cr.set_line_width(max(1.0, r * 0.14))
            for i in range(8):
                a = i * math.pi / 4
                cr.move_to(cx + ox + r * 0.63 * math.cos(a),
                           cy + oy + r * 0.63 * math.sin(a))
                cr.line_to(cx + ox + r * 0.92 * math.cos(a),
                           cy + oy + r * 0.92 * math.sin(a))
                cr.stroke()

        def _cloud(ox=0.0, oy=0.0, r=None, gray=0.82, alpha=0.92):
            r = r if r is not None else s * 0.50
            g = gray
            cr.push_group()
            cr.set_source_rgba(g, g + 0.02, g + 0.04, 1.0)
            for dx, dy, ri in [(-0.50, 0.12, 0.52),
                                ( 0.45, 0.12, 0.52),
                                (-0.05, -0.12, 0.70)]:
                cr.arc(cx + ox + dx * r, cy + oy + dy * r,
                       ri * r, 0, 2 * math.pi)
                cr.fill()
            cr.rectangle(cx + ox - r * 0.97, cy + oy + r * 0.02,
                         r * 1.94, r * 0.60)
            cr.fill()
            cr.pop_group_to_source()
            cr.paint_with_alpha(alpha)

        def _drops(n=2, ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            spacing = r * 0.38
            x0d = cx + ox - spacing * (n - 1) / 2
            for i in range(n):
                xi = x0d + i * spacing
                cr.set_source_rgba(0.40, 0.68, 1.00, 0.92)
                cr.set_line_width(max(1.2, r * 0.11))
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.move_to(xi, cy + oy + r * 0.44)
                cr.line_to(xi - r * 0.07, cy + oy + r * 0.72)
                cr.stroke()

        def _snow_dots(n=2, ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            spacing = r * 0.38
            x0d = cx + ox - spacing * (n - 1) / 2
            cr.set_source_rgba(0.78, 0.92, 1.00, 0.90)
            for i in range(n):
                xi = x0d + i * spacing
                yi = cy + oy + r * 0.60
                if size >= 22:
                    # small 6-arm asterisk
                    cr.set_line_width(max(1.0, r * 0.10))
                    cr.set_line_cap(cairo.LINE_CAP_ROUND)
                    arm = max(1.5, r * 0.14)
                    for a in (0, math.pi / 3, 2 * math.pi / 3):
                        cr.move_to(xi - arm * math.cos(a), yi - arm * math.sin(a))
                        cr.line_to(xi + arm * math.cos(a), yi + arm * math.sin(a))
                        cr.stroke()
                else:
                    cr.arc(xi, yi, max(1.5, r * 0.11), 0, 2 * math.pi)
                    cr.fill()

        def _bolt(ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            cr.set_source_rgba(1.00, 0.92, 0.18, 0.97)
            cr.set_line_width(max(1.5, r * 0.16))
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_join(cairo.LINE_JOIN_ROUND)
            pts = [(0.10, 0.08), (-0.08, 0.40),
                   (0.06, 0.40), (-0.10, 0.78)]
            cr.move_to(cx + ox + r * pts[0][0], cy + oy + r * pts[0][1])
            for px, py in pts[1:]:
                cr.line_to(cx + ox + r * px, cy + oy + r * py)
            cr.stroke()

        def _fog(ox=0.0, oy=0.0, r=None):
            r = r if r is not None else s
            cr.set_source_rgba(0.72, 0.78, 0.86, 0.80)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_line_width(max(1.5, r * 0.14))
            for yi_f, x1_f, x2_f in [(-0.30, -0.90, 0.90),
                                       ( 0.02, -0.75, 0.75),
                                       ( 0.34, -0.82, 0.60)]:
                cr.move_to(cx + ox + x1_f * r, cy + oy + yi_f * r)
                cr.line_to(cx + ox + x2_f * r, cy + oy + yi_f * r)
                cr.stroke()

        # ── symbol → composition ─────────────────────────────────────────────
        has_thunder  = 'thunder'  in sym
        has_rain     = 'rain'     in sym
        has_snow     = 'snow'     in sym
        has_sleet    = 'sleet'    in sym
        has_showers  = 'showers'  in sym
        has_heavy    = 'heavy'    in sym
        has_light    = 'light'    in sym
        is_sun_part  = has_showers and not has_thunder

        if sym == 'clearsky':
            _sun()
        elif sym == 'fair':
            _sun(ox=-s*0.14, oy=-s*0.18, r=s*0.36)
            _cloud(ox=s*0.10, oy=s*0.16, r=s*0.40, gray=0.76)
        elif sym == 'partlycloudy':
            _sun(ox=-s*0.20, oy=-s*0.22, r=s*0.32)
            _cloud(ox=s*0.08, oy=s*0.12, r=s*0.46, gray=0.74)
        elif sym in ('cloudy', 'overcast'):
            _cloud(r=s*0.54)
        elif sym == 'fog':
            _fog()
        elif has_thunder:
            cloud_gray = 0.42 if has_heavy else 0.52
            _cloud(oy=-s*0.14, r=s*0.46, gray=cloud_gray, alpha=0.95)
            if has_rain or has_sleet:
                _drops(1, ox=-s*0.25, oy=s*0.04)
            elif has_snow:
                _snow_dots(1, ox=-s*0.25, oy=s*0.04)
            _bolt(oy=s*0.06)
        else:
            # cloud + precipitation (with optional partial sun for showers)
            n_precip = 1 if has_light else (3 if has_heavy else 2)
            cloud_gray = 0.62 if has_heavy else (0.72 if has_light else 0.66)
            if is_sun_part:
                _sun(ox=-s*0.22, oy=-s*0.28, r=s*0.30)
                _cloud(ox=s*0.06, oy=s*0.10, r=s*0.44,
                       gray=cloud_gray, alpha=0.90)
            else:
                _cloud(oy=-s*0.12, r=s*0.46, gray=cloud_gray, alpha=0.92)
            if has_snow:
                _snow_dots(n_precip, oy=s*0.04)
            elif has_sleet:
                _drops(max(1, n_precip - 1), ox=-s*0.15, oy=s*0.04)
                _snow_dots(1, ox=s*0.20, oy=s*0.04)
            else:
                _drops(n_precip, oy=s*0.04)

        cr.restore()

    # ── Weekly forecast column (accordion) ───────────────────────────────────

    def _draw_weekly_forecast(self, cr, W, H):
        daily = self._clouds.get('daily_forecast', [])
        if not daily:
            self._weekly_card_rects = []
            return

        CARD_W   = 210
        DAY_H    = 52
        HOUR_H   = 28
        DAY_GAP  = 5
        HOUR_GAP = 2
        MARGIN   = 14
        x0       = W - CARD_W - MARGIN
        tz_off   = self.cfg.get('timezone_offset', 0)
        today_str = self._today_str

        # Compute max days that fit without overflowing screen height
        y_start  = 74
        max_h    = H - y_start - MARGIN
        n_hourly = len(self._selected_day_slots)
        expanded_h = (DAY_H + DAY_GAP) + n_hourly * (HOUR_H + HOUR_GAP) + DAY_GAP
        remaining  = max_h - expanded_h
        extra_days = max(0, int(remaining // (DAY_H + DAY_GAP)))
        # 1 selected day is always shown; up to 6 more fit
        max_days   = 1 + extra_days if self._selected_day else int(max_h // (DAY_H + DAY_GAP))
        max_days   = min(max_days, 7)

        rects = []
        y     = y_start

        for day in daily[:max_days]:
            date_str = day.get('date', '')
            sym      = day.get('symbol', '')
            temp_max = day.get('temp_max')
            temp_min = day.get('temp_min')
            precip   = day.get('precip', 0.0)
            accent   = _WX_ACCENT.get(sym, (0.72, 0.82, 1.00))
            cond_lbl = _WX_LABEL.get(sym, sym.replace('_', ' ').title() if sym else '--')
            selected = (self._selected_day == date_str)

            if date_str == today_str:
                day_name = _t('Today')
            else:
                try:
                    day_name = _day_name(datetime.date.fromisoformat(date_str).weekday())
                except Exception:
                    day_name = '--'

            # ── Day card ─────────────────────────────────────────────────────
            rects.append((date_str, x0, y, CARD_W, DAY_H))

            self._rrect(cr, x0, y, CARD_W, DAY_H, 9)
            cr.set_source_rgba(0.0, 0.0, 0.0, 0.62 if selected else 0.48)
            cr.fill_preserve()
            cr.set_source_rgba(*accent, 0.55 if selected else 0.20)
            cr.set_line_width(1.8 if selected else 1.0)
            cr.stroke()

            if selected:
                cr.set_source_rgba(*accent, 0.85)
                cr.rectangle(x0, y + 8, 3, DAY_H - 16)
                cr.fill()

            # Weather icon — centre of card
            self._draw_wx_icon(cr, x0 + 104, y + 26, 32, sym)

            # Left column: day name + condition
            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
            cr.set_font_size(11)
            cr.set_source_rgba(*accent, 1.0 if selected else 0.92)
            cr.move_to(x0 + 10, y + 20)
            cr.show_text(day_name)

            cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(9)
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.90 if selected else 0.68)
            cr.move_to(x0 + 10, y + 36)
            cr.show_text(_t(cond_lbl))

            if precip >= 0.2:
                cr.set_font_size(8.5)
                cr.set_source_rgba(0.50, 0.82, 1.00, 0.85)
                cr.move_to(x0 + 10, y + 48)
                cr.show_text(f"{precip:.1f} mm")

            if temp_max is not None:
                cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
                cr.set_font_size(15)
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
                s = f"{temp_max:.0f}°"
                te = cr.text_extents(s)
                cr.move_to(x0 + CARD_W - 12 - te.width, y + 22)
                cr.show_text(s)

            if temp_min is not None:
                cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
                cr.set_font_size(10)
                cr.set_source_rgba(0.75, 0.82, 1.0, 0.58)
                s = f"{temp_min:.0f}°"
                te = cr.text_extents(s)
                cr.move_to(x0 + CARD_W - 12 - te.width, y + 38)
                cr.show_text(s)

            y += DAY_H + DAY_GAP

            # ── Hourly accordion (only for selected day) ──────────────────────
            if selected:
                slots = self._selected_day_slots
                xi = x0 + 10   # indent hourly cards slightly
                wi = CARD_W - 10

                for slot in slots:
                    try:
                        raw = slot['ts'].rstrip('Z')
                        dt_local = (datetime.datetime.fromisoformat(raw)
                                    + datetime.timedelta(hours=tz_off))
                        time_lbl = f"{dt_local.hour:02d}:00"
                    except Exception:
                        time_lbl = '--:--'

                    sym_h    = slot.get('symbol', '')
                    cond_h   = _t(_WX_LABEL.get(sym_h,
                                                 sym_h.replace('_', ' ').title() if sym_h else '--'))
                    temp_h = slot.get('temp', 0.0)
                    prcp_h = slot.get('precip', 0.0)
                    acc_h  = _WX_ACCENT.get(sym_h, (0.72, 0.82, 1.00))

                    # Background
                    self._rrect(cr, xi, y, wi, HOUR_H, 6)
                    cr.set_source_rgba(0.04, 0.07, 0.16, 0.55)
                    cr.fill_preserve()
                    cr.set_source_rgba(*acc_h, 0.14)
                    cr.set_line_width(0.5)
                    cr.stroke()

                    ty = y + HOUR_H * 0.64

                    # Time — accent, bold
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD)
                    cr.set_font_size(9)
                    cr.set_source_rgba(*acc_h, 0.95)
                    cr.move_to(xi + 7, ty)
                    cr.show_text(time_lbl)

                    # Small weather icon
                    self._draw_wx_icon(cr, xi + 42, y + HOUR_H * 0.50, 18, sym_h)

                    # Condition (+ precip inline)
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_NORMAL)
                    cr.set_font_size(8.5)
                    if prcp_h >= 0.1:
                        cr.set_source_rgba(0.55, 0.85, 1.00, 0.85)
                        cr.move_to(xi + 56, ty)
                        cr.show_text(f"{cond_h}  {prcp_h:.1f}mm")
                    else:
                        cr.set_source_rgba(1.0, 1.0, 1.0, 0.72)
                        cr.move_to(xi + 56, ty)
                        cr.show_text(cond_h)

                    # Temperature — right-aligned, bold
                    cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL,
                                        cairo.FONT_WEIGHT_BOLD)
                    cr.set_font_size(10)
                    cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
                    t_str = f"{temp_h:.0f}°"
                    te = cr.text_extents(t_str)
                    cr.move_to(xi + wi - 8 - te.width, ty)
                    cr.show_text(t_str)

                    y += HOUR_H + HOUR_GAP

                y += DAY_GAP  # breathing room after expanded section

        self._weekly_card_rects = rects

    # ── HUD cards ────────────────────────────────────────────────────────────

    def _draw_cards(self, cr, W, H, now, sun_el, phase, age, m_el=None):
        cfg     = self.cfg
        enabled = cfg.get('cards', DEFAULT_CONFIG['cards'])
        lat, lon = cfg['latitude'], cfg['longitude']
        clouds  = self._clouds

        CW, CH, GAP = 198, 60, 10
        START_X     = 18
        START_Y     = H * 0.72
        col = row = 0

        IC = 20     # icon size in px
        ICA = 0.68  # icon alpha

        def emit(title, value, sub=None, icon_fn=None):
            nonlocal col, row
            cx = START_X + col * (CW + GAP)
            cy = START_Y + row * (CH + GAP)
            self._card(cr, cx, cy, CW, CH, title, value, sub)
            if icon_fn:
                cr.save()
                cr.new_path()   # clear current point left by _card's show_text
                icon_fn(cx + CW - IC - 8, cy + (CH - IC) / 2)
                cr.new_path()   # ensure nothing bleeds into next draw call
                cr.restore()
            col += 1
            if col >= 3:
                col = 0
                row += 1

        def ic_clock(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA)
            cr.set_line_width(1.3)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.stroke()
            # hour hand
            h_a = (now.hour % 12 + now.minute / 60) / 12 * 2 * math.pi - math.pi / 2
            cr.set_line_width(2.0)
            cr.move_to(icx, icy)
            cr.line_to(icx + (r - 4) * 0.58 * math.cos(h_a),
                       icy + (r - 4) * 0.58 * math.sin(h_a))
            cr.stroke()
            # minute hand
            m_a = now.minute / 60 * 2 * math.pi - math.pi / 2
            cr.set_line_width(1.2)
            cr.move_to(icx, icy)
            cr.line_to(icx + (r - 2) * 0.82 * math.cos(m_a),
                       icy + (r - 2) * 0.82 * math.sin(m_a))
            cr.stroke()
            cr.arc(icx, icy, 1.5, 0, 2 * math.pi)
            cr.fill()

        def ic_pin(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 0.9
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA)
            cr.set_line_width(1.3)
            # Circle body
            cr.arc(icx, icy - r * 0.30, r * 0.58, 0, 2 * math.pi)
            cr.stroke()
            # Inner dot
            cr.arc(icx, icy - r * 0.30, r * 0.20, 0, 2 * math.pi)
            cr.fill()
            # Pointed tail
            cr.move_to(icx - r * 0.48, icy - r * 0.08)
            cr.line_to(icx, icy + r * 0.88)
            cr.line_to(icx + r * 0.48, icy - r * 0.08)
            cr.stroke()

        def ic_sunrise(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.05
            cr.set_source_rgba(1.0, 0.75, 0.25, ICA)
            cr.set_line_width(1.3)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Horizon line
            cr.move_to(icx - r * 0.95, icy)
            cr.line_to(icx + r * 0.95, icy)
            cr.stroke()
            # Sun semi-circle
            cr.arc(icx, icy, r * 0.50, math.pi, 0)
            cr.stroke()
            # Rays (top only)
            for a_deg in (-60, -30, 0, 30, 60):
                a = math.radians(a_deg - 90)
                cr.move_to(icx + r * 0.65 * math.cos(a), icy + r * 0.65 * math.sin(a))
                cr.line_to(icx + r * 0.90 * math.cos(a), icy + r * 0.90 * math.sin(a))
                cr.stroke()
            # Up arrow
            cr.set_source_rgba(0.55, 1.0, 0.55, ICA * 0.80)
            cr.set_line_width(1.2)
            cr.move_to(icx, icy - r * 0.55)
            cr.line_to(icx, icy + r * 0.30)
            cr.stroke()
            cr.move_to(icx - r * 0.28, icy - r * 0.28)
            cr.line_to(icx, icy - r * 0.55)
            cr.line_to(icx + r * 0.28, icy - r * 0.28)
            cr.stroke()

        def ic_solar_noon(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.10
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA)
            cr.set_line_width(1.3)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Sun disc
            cr.arc(icx, icy - r * 0.35, r * 0.38, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA * 0.65)
            # Full rays around
            for i in range(8):
                a = i * math.pi / 4
                cr.move_to(icx + r * 0.55 * math.cos(a),
                           icy - r * 0.35 + r * 0.55 * math.sin(a))
                cr.line_to(icx + r * 0.80 * math.cos(a),
                           icy - r * 0.35 + r * 0.80 * math.sin(a))
                cr.stroke()
            # Horizon line
            cr.set_source_rgba(1.0, 0.88, 0.22, ICA * 0.45)
            cr.set_line_width(1.0)
            cr.move_to(icx - r * 0.95, icy + r * 0.65)
            cr.line_to(icx + r * 0.95, icy + r * 0.65)
            cr.stroke()

        def ic_moon_phase(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            # Dark disc
            cr.set_source_rgba(0.10, 0.12, 0.22, 0.90)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.fill()
            # Outline
            cr.set_source_rgba(0.75, 0.82, 1.0, ICA * 0.60)
            cr.set_line_width(0.8)
            cr.arc(icx, icy, r - 0.5, 0, 2 * math.pi)
            cr.stroke()
            # Lit crescent with correct limb orientation
            t = math.cos(phase * 2 * math.pi)
            cr.set_source_rgba(0.96, 0.94, 0.86, 0.95)
            cr.save()
            cr.translate(icx, icy)
            cr.rotate(-self._moon_limb_angle)
            rr = r - 1.5
            if t < -0.95:
                cr.arc(0, 0, rr, 0, 2 * math.pi)
                cr.fill()
            elif t > 0.95:
                pass  # new moon — nothing lit
            else:
                cr.move_to(0, -rr)
                cr.arc(0, 0, rr, -math.pi / 2, math.pi / 2)
                cr.save()
                cr.scale(t, 1.0)
                cr.arc_negative(0, 0, rr, math.pi / 2, -math.pi / 2)
                cr.restore()
                cr.close_path()
                cr.fill()
            cr.restore()

        def ic_moon_rise(ix, iy):
            r = IC / 2
            icx, icy = ix + r, iy + r
            cr.set_source_rgba(0.75, 0.82, 1.0, ICA)
            cr.set_line_width(1.2)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Crescent (simple left-facing)
            cr.arc(icx + r * 0.08, icy, r * 0.62, math.pi * 0.55, math.pi * 1.45)
            cr.stroke()
            cr.arc_negative(icx + r * 0.35, icy, r * 0.52,
                            math.pi * 1.45, math.pi * 0.55)
            cr.stroke()
            # Up/down arrows (rise left, set right)
            cr.set_source_rgba(0.55, 1.0, 0.55, ICA * 0.75)
            cr.set_line_width(1.0)
            ax = icx - r * 0.75
            cr.move_to(ax, icy + r * 0.25)
            cr.line_to(ax, icy - r * 0.60)
            cr.stroke()
            cr.move_to(ax - r * 0.22, icy - r * 0.35)
            cr.line_to(ax, icy - r * 0.60)
            cr.line_to(ax + r * 0.22, icy - r * 0.35)
            cr.stroke()
            cr.set_source_rgba(1.0, 0.60, 0.55, ICA * 0.75)
            ax2 = icx + r * 0.90
            cr.move_to(ax2, icy - r * 0.60)
            cr.line_to(ax2, icy + r * 0.25)
            cr.stroke()
            cr.move_to(ax2 - r * 0.22, icy + r * 0.0)
            cr.line_to(ax2, icy + r * 0.25)
            cr.line_to(ax2 + r * 0.22, icy + r * 0.0)
            cr.stroke()

        def ic_daylight(ix, iy, pct=0.5, is_night=False):
            r = IC / 2
            icx, icy = ix + r, iy + r * 1.05
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            # Track arc (full semicircle)
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA * 0.28)
            cr.set_line_width(2.5)
            cr.arc(icx, icy, r * 0.75, math.pi, 0)
            cr.stroke()
            if not is_night:
                # Elapsed arc
                cr.set_source_rgba(1.0, 0.80, 0.22, ICA * 0.85)
                end_a = math.pi - pct / 100.0 * math.pi
                cr.arc_negative(icx, icy, r * 0.75, math.pi, end_a)
                cr.stroke()
                # Sun position dot on arc
                sun_a = math.pi - pct / 100.0 * math.pi
                cr.set_source_rgba(1.0, 0.88, 0.22, 0.95)
                cr.arc(icx + r * 0.75 * math.cos(sun_a),
                       icy + r * 0.75 * math.sin(sun_a), 2.5, 0, 2 * math.pi)
                cr.fill()
            # Horizon base line
            cr.set_source_rgba(0.75, 0.85, 1.0, ICA * 0.40)
            cr.set_line_width(1.0)
            cr.move_to(icx - r * 0.85, icy)
            cr.line_to(icx + r * 0.85, icy)
            cr.stroke()

        # ── Cloud badge — top right (always) ─────────────────────────────────
        if enabled.get('cloud_cover', True):
            _wdirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE',
                      'S','SSW','SW','WSW','W','WNW','NW','NNW']
            _wlbl  = _wdirs[int((clouds.get('wind_dir', 0) + 11.25) / 22.5) % 16]
            extra  = ''
            if clouds.get('temp') is not None:
                extra += f"  · {clouds['temp']:.0f}°C"
            if clouds.get('wind_speed', 0) > 0.5:
                extra += f"  {_wlbl} {clouds['wind_speed']:.0f}m/s"
            self._card(cr, W - 216, 18, 198, 44, _t('CLOUD COVER'),
                       f"{clouds['total']}%",
                       f"Lo {clouds['low']}%  Mid {clouds['mid']}%  Hi {clouds['high']}%{extra}")
            # Cloud cover weather icon
            wx_sym = clouds.get('symbol', '')
            if wx_sym:
                cr.new_path()
                self._draw_wx_icon(cr, W - 216 + 198 - 18, 18 + 22, 28, wx_sym)

        if enabled.get('clock'):
            emit(_t('LOCAL TIME'), now.strftime('%H:%M:%S'),
                 _fmt_date(now), icon_fn=ic_clock)

        if enabled.get('location'):
            city = self._city_name
            if city:
                emit(_t('LOCATION'), city,
                     f"{'N' if lat >= 0 else 'S'}{abs(lat):.3f}°  "
                     f"{'E' if lon >= 0 else 'W'}{abs(lon):.3f}°",
                     icon_fn=ic_pin)
            else:
                emit(_t('LOCATION'),
                     f"{'N' if lat >= 0 else 'S'} {abs(lat):.4f}°",
                     f"{'E' if lon >= 0 else 'W'} {abs(lon):.4f}°",
                     icon_fn=ic_pin)

        if enabled.get('sunrise_sunset'):
            sr = self._sunrise.strftime('%H:%M') if self._sunrise else '--:--'
            ss = self._sunset.strftime('%H:%M')  if self._sunset  else '--:--'
            emit(_t('SUNRISE / SUNSET'), f'{sr}  ·  {ss}',
                 f'Solar elev: {sun_el:+.1f}°', icon_fn=ic_sunrise)

        if enabled.get('solar_noon'):
            sn = self._s_noon.strftime('%H:%M') if self._s_noon else '--:--'
            emit(_t('SOLAR NOON'), sn, f'Max elev: {self._max_el:.1f}°',
                 icon_fn=ic_solar_noon)

        if enabled.get('moon_phase'):
            el_str = f'  El: {m_el:+.1f}' if m_el is not None else ''
            emit(_t('MOON PHASE'), _t(_PHASE_NAMES[int(phase * 8) % 8]),
                 f'Age: {age:.1f}d{el_str}', icon_fn=ic_moon_phase)

        if enabled.get('moon_rise_set'):
            mr = self._moonrise.strftime('%H:%M') if self._moonrise else '--:--'
            ms = self._moonset.strftime('%H:%M')  if self._moonset  else '--:--'
            emit(_t('MOONRISE / MOONSET'), f'{mr}  /  {ms}', icon_fn=ic_moon_rise)

        if enabled.get('daylight_remaining') and self._sunrise and self._sunset:
            now_s = now.hour * 3600 + now.minute * 60 + now.second
            sr_s  = self._sunrise.hour * 3600 + self._sunrise.minute * 60
            ss_s  = self._sunset.hour  * 3600 + self._sunset.minute  * 60
            if sr_s <= now_s <= ss_s:
                rem = ss_s - now_s
                pct = (now_s - sr_s) / max(1, ss_s - sr_s) * 100
                emit(_t('DAYLIGHT LEFT'),
                     f'{rem // 3600}h {(rem % 3600) // 60:02d}m',
                     _t('pct_elapsed').format(pct=int(pct)),
                     icon_fn=lambda ix, iy, p=pct: ic_daylight(ix, iy, p, False))
            else:
                until = (sr_s - now_s) % 86400
                emit(_t('DAYLIGHT LEFT'),
                     _t('sunrise_in').format(h=until // 3600, m=(until % 3600) // 60),
                     _t('Night'),
                     icon_fn=lambda ix, iy: ic_daylight(ix, iy, 0, True))

    def _card(self, cr, x, y, w, h, title, value, sub=None):
        cr.save()
        self._rrect(cr, x, y, w, h, 9)
        cr.set_source_rgba(0, 0, 0, 0.42)
        cr.fill_preserve()
        cr.set_source_rgba(1, 1, 1, 0.13)
        cr.set_line_width(1)
        cr.stroke()

        cr.select_font_face('Sans', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(9.5)
        cr.set_source_rgba(0.75, 0.82, 1.0, 0.70)
        cr.move_to(x + 11, y + 17)
        cr.show_text(title)

        cr.set_font_size(15.5)
        cr.set_source_rgba(1, 1, 1, 0.95)
        cr.move_to(x + 11, y + 37)
        cr.show_text(value)

        if sub:
            cr.set_font_size(9)
            cr.set_source_rgba(0.65, 0.78, 1.0, 0.60)
            cr.move_to(x + 11, y + h - 6)
            cr.show_text(sub)
        cr.restore()

    def _rrect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r,     r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r,  0,            math.pi / 2)
        cr.arc(x + r,     y + h - r, r,  math.pi / 2,  math.pi)
        cr.arc(x + r,     y + r,     r,  math.pi,      3 * math.pi / 2)
        cr.close_path()


# ─── Timezone list ───────────────────────────────────────────────────────────
# (utc_offset_hours, display_label)
_TZ_LIST = [
    (-12,   'UTC-12'),
    (-11,   'UTC-11  (Samoa, Niue)'),
    (-10,   'UTC-10  (Hawaii)'),
    (-9.5,  'UTC-09:30  (Marquesas)'),
    (-9,    'UTC-09  (Alaska)'),
    (-8,    'UTC-08  (Los Angeles, Vancouver)'),
    (-7,    'UTC-07  (Denver, Phoenix)'),
    (-6,    'UTC-06  (Chicago, Mexico City)'),
    (-5,    'UTC-05  (New York, Lima, Bogota)'),
    (-4,    'UTC-04  (Santiago, Caracas, Halifax)'),
    (-3.5,  'UTC-03:30  (Newfoundland)'),
    (-3,    'UTC-03  (Buenos Aires, Brasilia, Montevideo)'),
    (-2,    'UTC-02  (South Georgia)'),
    (-1,    'UTC-01  (Azores, Cape Verde)'),
    ( 0,    'UTC+00  (London, Lisbon, Accra, Lome, Abidjan)'),
    ( 1,    'UTC+01  (Paris, Berlin, Lagos, Kinshasa, Madrid)'),
    ( 2,    'UTC+02  (Cairo, Johannesburg, Athens, Helsinki)'),
    ( 3,    'UTC+03  (Nairobi, Moscow, Riyadh, Istanbul)'),
    ( 3.5,  'UTC+03:30  (Tehran)'),
    ( 4,    'UTC+04  (Dubai, Baku, Tbilisi)'),
    ( 4.5,  'UTC+04:30  (Kabul)'),
    ( 5,    'UTC+05  (Karachi, Tashkent, Yekaterinburg)'),
    ( 5.5,  'UTC+05:30  (Mumbai, Delhi, Colombo)'),
    ( 5.75, 'UTC+05:45  (Kathmandu)'),
    ( 6,    'UTC+06  (Dhaka, Almaty, Bishkek)'),
    ( 6.5,  'UTC+06:30  (Yangon)'),
    ( 7,    'UTC+07  (Bangkok, Jakarta, Hanoi)'),
    ( 8,    'UTC+08  (Beijing, Singapore, Perth, Manila)'),
    ( 8.75, 'UTC+08:45  (Eucla)'),
    ( 9,    'UTC+09  (Tokyo, Seoul, Yakutsk)'),
    ( 9.5,  'UTC+09:30  (Adelaide, Darwin)'),
    (10,    'UTC+10  (Sydney, Melbourne, Vladivostok)'),
    (10.5,  'UTC+10:30  (Lord Howe)'),
    (11,    'UTC+11  (Solomon Islands, Noumea)'),
    (12,    'UTC+12  (Auckland, Fiji, Kamchatka)'),
    (12.75, 'UTC+12:45  (Chatham Islands)'),
    (13,    'UTC+13  (Apia, Nuku\'alofa)'),
    (14,    'UTC+14  (Kiribati, Line Islands)'),
]

def _tz_index(offset):
    """Return the index in _TZ_LIST closest to offset."""
    best, best_d = 0, float('inf')
    for i, (o, _) in enumerate(_TZ_LIST):
        d = abs(o - offset)
        if d < best_d:
            best, best_d = i, d
    return best

# ─── Facing-direction options ────────────────────────────────────────────────
# (azimuth_degrees, compass_abbrev, direction_i18n_key)
_FACING_OPTIONS = [
    (  0, 'N',  'Facing North'),
    ( 45, 'NE', 'Facing North-East'),
    ( 90, 'E',  'Facing East'),
    (135, 'SE', 'Facing South-East'),
    (180, 'S',  'Facing South (default)'),
    (225, 'SW', 'Facing South-West'),
    (270, 'W',  'Facing West'),
    (315, 'NW', 'Facing North-West'),
]

# ─── Settings dialog ──────────────────────────────────────────────────────────

class SettingsDialog(Gtk.Window):

    def __init__(self, parent):
        super().__init__(title='Caelum — Settings')
        self.par = parent
        self.cfg = parent.cfg
        self.set_default_size(330, 540)
        self.set_transient_for(parent)
        self.set_destroy_with_parent(True)
        self.set_resizable(False)

        outer  = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        outer.pack_start(scroll, True, True, 0)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)
        box.set_margin_bottom(8)
        box.set_margin_start(18)
        box.set_margin_end(18)
        scroll.add(box)

        # ── Language ─────────────────────────────────────────────────────────
        lang_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lang_lbl = Gtk.Label(label=_t('Language'), xalign=0)
        lang_lbl.set_hexpand(True)
        self._lang_combo = Gtk.ComboBoxText()
        cur_lang = self.cfg.get('language', 'auto')
        for code, label in _LANG_OPTIONS:
            self._lang_combo.append(code, label)
        self._lang_combo.set_active_id(cur_lang if cur_lang in dict(_LANG_OPTIONS) else 'auto')
        self._lang_combo.connect('changed', self._on_lang_changed)
        lang_row.pack_start(lang_lbl, True, True, 0)
        lang_row.pack_end(self._lang_combo, False, False, 0)
        box.pack_start(lang_row, False, False, 2)

        box.pack_start(Gtk.Separator(), False, False, 4)

        # ── Master on/off ────────────────────────────────────────────────────
        on_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        on_lbl = Gtk.Label(xalign=0)
        on_lbl.set_markup(f'<b>{_t("Sky Overlay Active")}</b>')
        on_lbl.set_hexpand(True)
        sw_on = Gtk.Switch()
        sw_on.set_active(self.cfg.get('app_enabled', True))
        sw_on.connect('notify::active', lambda s, p: (
            self.cfg.update({'app_enabled': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        on_row.pack_start(on_lbl, True, True, 0)
        on_row.pack_end(sw_on, False, False, 0)
        box.pack_start(on_row, False, False, 2)

        as_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        as_lbl = Gtk.Label(label=_t('Start with GNOME session'), xalign=0)
        as_lbl.set_hexpand(True)
        sw_as = Gtk.Switch()
        sw_as.set_active(autostart_enabled())
        sw_as.connect('notify::active', lambda s, p: set_autostart(s.get_active()))
        as_row.pack_start(as_lbl, True, True, 0)
        as_row.pack_end(sw_as, False, False, 0)
        box.pack_start(as_row, False, False, 2)

        box.pack_start(Gtk.Separator(), False, False, 6)

        box.pack_start(Gtk.Label(label=_t('Aster Size'), xalign=0), False, False, 0)
        sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.5, 3.0, 0.1)
        sc.set_value(self.cfg.get('aster_scale', 1.0))
        sc.set_digits(1)
        sc.connect('value-changed', lambda s: (
            self.cfg.update({'aster_scale': s.get_value()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        box.pack_start(sc, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        row_ic = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l_ic   = Gtk.Label(label=_t('Astronomical Info Cards'), xalign=0)
        l_ic.set_hexpand(True)
        sw_ic  = Gtk.Switch()
        sw_ic.set_active(self.cfg.get('show_info_cards', False))
        sw_ic.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_info_cards': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row_ic.pack_start(l_ic, True, True, 0)
        row_ic.pack_end(sw_ic, False, False, 0)
        box.pack_start(row_ic, False, False, 2)

        box.pack_start(Gtk.Label(label=_t('Visible Cards'), xalign=0), False, False, 0)

        card_labels = {
            'clock':              _t('Clock & Date'),
            'location':           _t('Location & Coordinates'),
            'sunrise_sunset':     _t('Sunrise & Sunset'),
            'solar_noon':         _t('Solar Noon & Elevation'),
            'moon_phase':         _t('Moon Phase & Age'),
            'moon_rise_set':      _t('Moon Rise & Set'),
            'daylight_remaining': _t('Daylight Remaining'),
            'cloud_cover':        _t('Cloud Cover'),
        }
        cards = self.cfg.setdefault('cards', dict(DEFAULT_CONFIG['cards']))
        for key, lbl in card_labels.items():
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            l   = Gtk.Label(label=lbl, xalign=0)
            l.set_hexpand(True)
            sw  = Gtk.Switch()
            sw.set_active(cards.get(key, True))
            sw.connect('notify::active', self._card_toggle, key)
            row.pack_start(l, True, True, 0)
            row.pack_end(sw, False, False, 0)
            box.pack_start(row, False, False, 2)

        box.pack_start(Gtk.Separator(), False, False, 6)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l   = Gtk.Label(label=_t('Clean Mode  (Ctrl+H)'), xalign=0)
        l.set_hexpand(True)
        sw_c = Gtk.Switch()
        sw_c.set_active(self.cfg.get('clean_mode', False))
        sw_c.connect('notify::active', lambda s, p: (
            self.cfg.update({'clean_mode': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row.pack_start(l, True, True, 0)
        row.pack_end(sw_c, False, False, 0)
        box.pack_start(row, False, False, 2)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l2   = Gtk.Label(label=_t('Constellation Lines'), xalign=0)
        l2.set_hexpand(True)
        sw_k = Gtk.Switch()
        sw_k.set_active(self.cfg.get('show_constellations', True))
        sw_k.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_constellations': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row2.pack_start(l2, True, True, 0)
        row2.pack_end(sw_k, False, False, 0)
        box.pack_start(row2, False, False, 2)

        row3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l3   = Gtk.Label(label=_t('Horizon Silhouette'), xalign=0)
        l3.set_hexpand(True)
        sw_sil = Gtk.Switch()
        sw_sil.set_active(self.cfg.get('show_silhouette', True))
        sw_sil.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_silhouette': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row3.pack_start(l3, True, True, 0)
        row3.pack_end(sw_sil, False, False, 0)
        box.pack_start(row3, False, False, 2)

        row4 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l4   = Gtk.Label(label=_t('Compass Rose'), xalign=0)
        l4.set_hexpand(True)
        sw_cmp = Gtk.Switch()
        sw_cmp.set_active(self.cfg.get('show_compass', True))
        sw_cmp.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_compass': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row4.pack_start(l4, True, True, 0)
        row4.pack_end(sw_cmp, False, False, 0)
        box.pack_start(row4, False, False, 2)

        row5 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l5   = Gtk.Label(label=_t('Horizon Direction Labels'), xalign=0)
        l5.set_hexpand(True)
        sw_hl = Gtk.Switch()
        sw_hl.set_active(self.cfg.get('show_horizon_labels', True))
        sw_hl.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_horizon_labels': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row5.pack_start(l5, True, True, 0)
        row5.pack_end(sw_hl, False, False, 0)
        box.pack_start(row5, False, False, 2)

        row6 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l6   = Gtk.Label(label=_t('Rainbow'), xalign=0)
        l6.set_hexpand(True)
        sw_rb = Gtk.Switch()
        sw_rb.set_active(self.cfg.get('show_rainbow', True))
        sw_rb.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_rainbow': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row6.pack_start(l6, True, True, 0)
        row6.pack_end(sw_rb, False, False, 0)
        box.pack_start(row6, False, False, 2)

        row8b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        l8b   = Gtk.Label(label=_t('Weekly Forecast Column'), xalign=0)
        l8b.set_hexpand(True)
        sw_wf = Gtk.Switch()
        sw_wf.set_active(self.cfg.get('show_weekly_forecast', True))
        sw_wf.connect('notify::active', lambda s, p: (
            self.cfg.update({'show_weekly_forecast': s.get_active()}),
            save_config(self.cfg), self.par.da.queue_draw()))
        row8b.pack_start(l8b, True, True, 0)
        row8b.pack_end(sw_wf, False, False, 0)
        box.pack_start(row8b, False, False, 2)

        box.pack_start(Gtk.Label(label=_t('Export sky as wallpaper'), xalign=0),
                       False, False, 2)
        _LS_OPTIONS = [
            ('off',        _t('Disabled')),
            ('background', _t('Desktop background only')),
            ('lockscreen', _t('Lock screen only')),
            ('both',       _t('Both background & lock screen')),
        ]
        ls_combo = Gtk.ComboBoxText()
        cur_ls   = self.cfg.get('lockscreen_export', 'off')
        for key, label in _LS_OPTIONS:
            ls_combo.append(key, label)
        ls_combo.set_active_id(cur_ls if cur_ls in dict(_LS_OPTIONS) else 'off')
        def _on_ls_changed(combo):
            mode = combo.get_active_id() or 'off'
            self.cfg.update({'lockscreen_export': mode})
            save_config(self.cfg)
            self.par._export_lockscreen_bg()
        ls_combo.connect('changed', _on_ls_changed)
        box.pack_start(ls_combo, False, False, 2)

        # ── Compass sensor status & serial port ──────────────────────────────
        hw_cmp   = getattr(self.par, '_has_compass', False)
        cmp_stat = getattr(self.par, '_compass_status', 'Not detected')
        self._cmp_status_lbl = Gtk.Label(xalign=0)
        self._cmp_status_lbl.set_markup(f'<small>Compass: <b>{cmp_stat}</b></small>')
        box.pack_start(self._cmp_status_lbl, False, False, 2)

        # Serial port entry
        box.pack_start(Gtk.Label(label=_t('External serial compass port'), xalign=0),
                       False, False, 2)
        port_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._e_compass_port = Gtk.Entry()
        self._e_compass_port.set_placeholder_text('/dev/ttyUSB0')
        self._e_compass_port.set_text(self.cfg.get('compass_port', ''))
        self._e_compass_port.set_hexpand(True)
        conn_btn = Gtk.Button(label=_t('Connect'))
        conn_btn.connect('clicked', self._connect_compass)
        port_row.pack_start(self._e_compass_port, True, True, 0)
        port_row.pack_start(conn_btn, False, False, 0)
        box.pack_start(port_row, False, False, 0)

        hint_serial = Gtk.Label(xalign=0)
        hint_serial.set_markup('<small>Arduino/USB dongle sends heading as plain number per line.\n'
                               'Install: <tt>sudo apt install python3-serial</tt></small>')
        hint_serial.set_line_wrap(True)
        box.pack_start(hint_serial, False, False, 2)

        if not hw_cmp:
            box.pack_start(Gtk.Label(label=_t('Screen facing direction'), xalign=0), False, False, 2)
            self._facing_combo = Gtk.ComboBoxText()
            cur_facing = float(self.cfg.get('facing', 180.0))
            for _, abbrev, dir_key in _FACING_OPTIONS:
                self._facing_combo.append_text(f'{abbrev}  — {_t(dir_key)}')
            best_i = min(range(len(_FACING_OPTIONS)),
                         key=lambda i: abs(_FACING_OPTIONS[i][0] - cur_facing))
            self._facing_combo.set_active(best_i)
            self._facing_combo.connect('changed', self._on_facing_changed)
            box.pack_start(self._facing_combo, False, False, 0)

        box.pack_start(Gtk.Separator(), False, False, 6)

        # ── Location ─────────────────────────────────────────────────────────
        box.pack_start(Gtk.Label(label=_t('Location'), xalign=0), False, False, 0)

        det_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        det_btn = Gtk.Button(label=_t('Detect automatically'))
        det_btn.connect('clicked', self._detect_location)
        self._det_status = Gtk.Label(label='', xalign=0)
        self._det_status.set_hexpand(True)
        self._det_status.set_line_wrap(True)
        det_row.pack_start(det_btn, False, False, 0)
        det_row.pack_start(self._det_status, True, True, 0)
        box.pack_start(det_row, False, False, 2)

        for lbl, key, default in [
            (_t('Latitude  (+N / -S)'), 'latitude',  6.1375),
            (_t('Longitude (+E / -W)'), 'longitude', 1.2123),
        ]:
            box.pack_start(Gtk.Label(label=lbl, xalign=0), False, False, 2)
            e = Gtk.Entry()
            e.set_text(str(self.cfg.get(key, default)))
            setattr(self, f'_e_{key}', e)
            box.pack_start(e, False, False, 0)

        # ── Timezone ─────────────────────────────────────────────────────────
        box.pack_start(Gtk.Label(label=_t('Timezone'), xalign=0), False, False, 2)
        self._tz_combo = Gtk.ComboBoxText()
        cur_idx = _tz_index(self.cfg.get('timezone_offset', 0))
        for offset, label in _TZ_LIST:
            self._tz_combo.append_text(label)
        self._tz_combo.set_active(cur_idx)
        box.pack_start(self._tz_combo, False, False, 0)

        btn = Gtk.Button(label=_t('Save & Apply'))
        btn.set_margin_top(10)
        btn.connect('clicked', self._save)
        box.pack_start(btn, False, False, 0)

        hint = Gtk.Label(xalign=0)
        hint.set_markup('<small>Right-click or click the gear to reopen this dialog.\n'
                        'Weather refreshes every 30 min via Open-Meteo.</small>')
        hint.set_margin_top(4)
        box.pack_start(hint, False, False, 0)

    def _on_lang_changed(self, combo):
        code = combo.get_active_id() or 'auto'
        self.cfg['language'] = code
        save_config(self.cfg)
        _set_lang(code)
        self.par.da.queue_draw()

    def _connect_compass(self, _btn):
        self.cfg['compass_port'] = self._e_compass_port.get_text().strip()
        save_config(self.cfg)
        self.par._detect_compass()
        if self.par._has_compass:
            GLib.timeout_add(500, self.par._poll_compass)
        status = getattr(self.par, '_compass_status', 'Not detected')
        self._cmp_status_lbl.set_markup(f'<small>Compass: <b>{status}</b></small>')
        self.par.da.queue_draw()

    def _on_facing_changed(self, combo):
        idx = combo.get_active()
        if 0 <= idx < len(_FACING_OPTIONS):
            self.cfg['facing'] = float(_FACING_OPTIONS[idx][0])
            save_config(self.cfg)
            self.par.da.queue_draw()

    def _card_toggle(self, sw, _param, key):
        self.cfg['cards'][key] = sw.get_active()
        save_config(self.cfg)
        self.par.da.queue_draw()

    def _detect_location(self, _btn):
        self._det_status.set_text('Detecting...')
        def _work():
            try:
                url = 'http://ip-api.com/json/?fields=status,lat,lon,timezone,offset'
                with urllib.request.urlopen(url, timeout=10) as r:
                    data = json.loads(r.read().decode())
                if data.get('status') == 'success':
                    GLib.idle_add(self._apply_location, data)
                else:
                    GLib.idle_add(self._det_status.set_text, 'Detection failed')
            except Exception as exc:
                GLib.idle_add(self._det_status.set_text, f'Error: {exc}')
        threading.Thread(target=_work, daemon=True).start()

    def _apply_location(self, data):
        lat    = data.get('lat', 6.1375)
        lon    = data.get('lon', 1.2123)
        offset = data.get('offset', 0) / 3600.0
        tz_name = data.get('timezone', '')
        self._e_latitude.set_text(f'{lat:.4f}')
        self._e_longitude.set_text(f'{lon:.4f}')
        self._tz_combo.set_active(_tz_index(offset))
        self._det_status.set_markup(f'<small>{tz_name}  ({lat:.4f}, {lon:.4f})</small>')
        return False

    def _save(self, _btn):
        try:
            self.cfg['latitude']  = float(self._e_latitude.get_text())
            self.cfg['longitude'] = float(self._e_longitude.get_text())
            idx = self._tz_combo.get_active()
            if 0 <= idx < len(_TZ_LIST):
                self.cfg['timezone_offset'] = _TZ_LIST[idx][0]
            save_config(self.cfg)
            self.par._refresh_day()
            self.par._selected_day       = None
            self.par._selected_day_slots = []
            self.par._fetch_weather_async()
            self.par._city_name = None
            self.par._fetch_city_name()
            self.par.da.queue_draw()
        except ValueError:
            pass


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    win = SkyTracker()
    win.connect('destroy', Gtk.main_quit)
    Gtk.main()
