#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Reference data for the tests (port of the dashboard's factory_setup).

The usage types, NCRIS facilities and ARDC programs mirror the data the
old Django data migrations seeded (usage types and facilities in full, a
representative set of ARDC programs and projects).
"""

from rcallocation import choices
from rcallocation.tests.unit import factories


USAGE_TYPES = [
    'Hosting services to support research',
    'Collaboration platform',
    'Hosting a website',
    'Hosting a database',
    'Hosting and sharing data',
    'Collaborating with other institutions',
    'Collaborating internationally',
    'Machine learning',
    'Data analysis',
    'Modelling and simulation',
    'Other',
]

NCRIS_FACILITIES = [
    ("Astronomy Australia Ltd", "AAL"),
    ("Atlas of Living Australia", "ALA"),
    ("AuScope", "AuScope"),
    ("Australian Centre for Disease Preparedness", "ACDP"),
    ("Australian National Fabrication Facility", "ANFF"),
    ("Australian Plant Phenomics Facility", "APPF"),
    ("Australian Urban Research Infrastructure Network", "AURIN"),
    ("Bioplatforms Australia", "BPA"),
    ("Heavy Ion Accelerators", "HIA"),
    ("Integrated Marine Observing System", "IMOS"),
    ("Microscopy Australia", "MA"),
    ("National Computational Infrastructure", "NCI"),
    ("National Deuteration Facility", "NDF"),
    ("National Imaging Facility", "NIF"),
    ("Nuclear Science Facilities", "NSF"),
    ("Pawsey Supercomputing Centre", "Pawsey"),
    ("Phenomics Australia", "PA"),
    ("Population Health Research Network", "PHRN"),
    ("Terrestrial Ecosystem Research Network", "TERN"),
    ("Therapeutic Innovation Australia", "TIA"),
    ("NCRIS Pilot project", "Pilot"),
    ("Other NCRIS support", "Other"),
]

# (short_name, name, project, explain, rank)
ARDC_SUPPORT = [
    ("Platforms", "ARDC Platforms program", False, True, 40),
    ("NDA", "ARDC National Data Assets program", False, True, 40),
    (
        "Alveo",
        "A Virtual Lab for Human Communication Science",
        True,
        False,
        30,
    ),
    ("ASVO", "All-Sky Virtual Observatory", True, False, 30),
    (
        "BCCVL",
        "Biodiversity and Climate Change Virtual Laboratory",
        True,
        False,
        30,
    ),
    ("CVL", "Characterization Virtual Laboratory", True, False, 30),
    ("CWSLab", "Climate and Weather Science Lab", True, False, 30),
    (
        "FAIMS",
        "Field Acquired Information Management Systems",
        True,
        False,
        30,
    ),
    ("GVL", "Genomics Virtual Laboratory", True, False, 30),
    ("HuNI", "Humanities Networked Infrastructure", True, False, 30),
    ("IEL", "Industrial Ecology Lab", True, False, 30),
    ("Nectar", "Nectar Research Cloud", False, True, 60),
    ("Other", "Other projects not covered above", False, True, 70),
]

ORGANISATIONS = [
    dict(
        short_name='QCIF',
        full_name='Queensland Cyber Infrastructure Foundation',
        ror_id='https://ror.org/12345678',
        country='AU',
    ),
    dict(
        short_name='Monash',
        full_name='Monash University',
        ror_id='https://ror.org/23456789',
        country='AU',
    ),
    dict(
        short_name='UWW',
        full_name='University of Woop Woop',
        ror_id='',
        country='AU',
        enabled=False,
    ),
    dict(
        short_name=choices.ORG_ALL_SHORT_NAME,
        full_name=choices.ORG_ALL_FULL_NAME,
        ror_id='',
        country='AU',
    ),
]


def seed_reference_data():
    for name in factories.ALL_SITES:
        factories.create_site(name, display_name=name)
    qcif = factories.get(factories.models.Site, name="qcif")
    uom = factories.get(factories.models.Site, name="uom")
    factories.create_approver("test_user", "One", sites=[qcif])
    factories.create_approver("test_user2", "Two", sites=[uom])
    factories.create_approver("test_user3", "Three")

    for org in ORGANISATIONS:
        factories.create_organisation(**org)

    for name in USAGE_TYPES:
        factories.create_usage_type(name)
    # To test handling of disabled UsageTypes
    factories.create_usage_type("Disabled", enabled=False)

    for name, short_name in NCRIS_FACILITIES:
        factories.create_ncris_facility(name, short_name)
    for short_name, name, project, explain, rank in ARDC_SUPPORT:
        factories.create_ardc_support(
            name, short_name, project=project, explain=explain, rank=rank
        )

    melbourne = factories.create_zone('melbourne')
    monash = factories.create_zone('monash')
    tas = factories.create_zone('tas')
    nectar = factories.create_zone('nectar')
    pawsey = factories.create_zone('pawsey')
    disabled_zone = factories.create_zone('disabled-zone', enabled=False)
    # Needed for checker tests as we use this zone
    factories.create_zone('QRIScloud')

    volume_st = factories.create_service_type(
        'volume',
        zones=[melbourne, monash, tas, disabled_zone],
        location_specific=True,
    )
    object_st = factories.create_service_type('object', zones=[nectar])
    compute_st = factories.create_service_type('compute', zones=[nectar])
    network_st = factories.create_service_type('network', zones=[nectar])
    rating_st = factories.create_service_type('rating', zones=[nectar])
    factories.create_service_type(
        'ls-service-type', zones=[pawsey], location_specific=True
    )
    ls_st = factories.get(
        factories.models.ServiceType, catalog_name='ls-service-type'
    )

    factories.create_resource('gigabytes', volume_st)
    objects = factories.create_resource('object', object_st)
    factories.create_resource('object', ls_st)
    cores = factories.create_resource('cores', compute_st)
    instances = factories.create_resource('instances', compute_st)
    ram = factories.create_resource('ram', compute_st, requestable=False)
    budget = factories.create_resource('budget', rating_st, name="Budget")
    router = factories.create_resource('router', network_st)
    network = factories.create_resource('network', network_st)
    lb = factories.create_resource('loadbalancer', network_st)
    fip = factories.create_resource('floatingip', network_st)

    gold = factories.create_bundle('gold', nectar, 16000)
    silver = factories.create_bundle('silver', nectar, 8000)
    bronze = factories.create_bundle('bronze', nectar, 4000)

    for bundle, scale in ((gold, 4), (silver, 2), (bronze, 1)):
        factories.create_bundle_quota(bundle, objects, 50 * scale)
        factories.create_bundle_quota(bundle, cores, 50 * scale)
        factories.create_bundle_quota(bundle, instances, 50 * scale)
        factories.create_bundle_quota(bundle, ram, 500 * scale)
        factories.create_bundle_quota(bundle, budget, 500 * scale)
        factories.create_bundle_quota(bundle, router, 5 * scale)
        factories.create_bundle_quota(bundle, network, 5 * scale)
        factories.create_bundle_quota(bundle, lb, 5 * scale)
        factories.create_bundle_quota(bundle, fip, 5 * scale)
