import argparse
import json
import os
import time
import bittensor as bt
import uuid
import asyncio
from dataclasses import asdict

from shared.veridex_protocol import SourceEvidence
from validator.snippet_validator import SnippetValidator

# List of SourceEvidence related to aliens
evidences = [
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/exoplanets/search-for-life/",
        excerpt="Our galaxy likely holds at least 100 billion planets, but so far, we have no evidence of life beyond Earth."
    ),
    SourceEvidence(
        url="https://www.seti.org/why-look-extraterrestrial-life",
        excerpt="Most researchers think there must be life elsewhere in the cosmos, and polls show that the public generally agrees."
    ),
    SourceEvidence(
        url="https://www.space.com/25325-fermi-paradox.html",
        excerpt="Discover the Fermi Paradox — why, in a vast universe full of stars and planets, haven't we found extraterrestrial life?"
    ),
    SourceEvidence(
        url="https://www.scientificamerican.com/article/how-many-aliens-are-in-the-milky-way-astronomers-turn-to-statistics-for-answers/",
        excerpt="The tenets of Thomas Bayes underpin the latest estimates of the prevalence of extraterrestrial life."
    ),
    SourceEvidence(
        url="https://www.nationalgeographic.com/astrobiology/",
        excerpt="Astrobiologist Kevin Hand prepares to deploy a rover beneath the ice of Alaska's Sukok Lake, modeling future searches for life on Europa."
    ),
    SourceEvidence(
        url="https://www.npr.org/2024/03/08/1237100622/pentagon-ufo-report-no-evidence-alien-technology",
        excerpt="The Pentagon says it found no evidence of extraterrestrial spacecraft in a new report reviewing nearly eight decades of UFO sightings."
    ),
    SourceEvidence(
        url="https://www.cnet.com/science/the-upcoming-pentagon-ufo-report-isnt-the-place-to-look-for-the-truth/",
        excerpt="UFOs are real but that doesn't mean we've been visited by aliens. The US government says there's no evidence."
    ),
    SourceEvidence(
        url="https://science.nasa.gov/universe/exoplanets/are-we-alone-in-the-universe-revisiting-the-drake-equation/",
        excerpt="Two researchers have revised the Drake equation, a mathematical formula for the probability of finding life or advanced civilizations in the universe."
    ),
    SourceEvidence(
        url="https://www.seti.org/event/search-life-beyond-earth-how-its-done-where-it-stands-and-why-it-matters",
        excerpt="SETI Institute CEO Bill Diamond describes the science behind the search for life beyond Earth and why it matters to humankind."
    ),
    SourceEvidence(
        url="https://www.space.com/fermi-paradox-aliens-contact-earth-not-interesting",
        excerpt="A new Fermi Paradox analysis suggests aliens haven't contacted Earth because we're not that interesting yet."
    ),
]

def get_config():
    parser = argparse.ArgumentParser()
    parser.add_argument("--custom", default="my_custom_value", help="Custom value")
    parser.add_argument("--netuid", type=int, default=1, help="Chain subnet uid")
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    bt.wallet.add_args(parser)
    bt.axon.add_args(parser)
    config = bt.config(parser)

    bt.logging.info(f"get_config: {config}")
    config.full_path = os.path.expanduser(
        "{}/{}/{}/netuid{}/validator".format(
            config.logging.logging_dir,
            config.wallet.name,
            config.wallet.hotkey_str,
            config.netuid,
        )
    )
    os.makedirs(config.full_path, exist_ok=True)
    return config

def setup_logging():
    config = get_config()
    bt.logging(config=config, logging_dir=config.full_path)
    bt.logging.info("Starting APIQueryHandler with config:")
    bt.logging.info(config)


# The main routine
async def main(num_calls: int):
    miner_uid = 1

    start = time.perf_counter()
    try:
        validator = SnippetValidator()
        # Create tasks
        tasks = [
            validator.validate_miner_snippet(str(uuid.uuid4()), miner_uid, evidence)
            for evidence in evidences[:num_calls]
        ]

        # Run all tasks concurrently
        results = await asyncio.gather(*tasks)
    finally:
        duration = time.perf_counter() - start
        print(f"Time taken for {num_calls}:  {duration:.4f} seconds")
    # Process results
    for res in results:
        print("Result:", json.dumps(asdict(res)))

# Entry point
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SnippetValidator X times.")
    parser.add_argument("--num-calls", type=int, default=1, help="Number of validator calls to run")
    args = parser.parse_args()

    asyncio.run(main(args.num_calls))
