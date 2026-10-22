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

"""Choice constants shared by the models, schemas and templates.

These were spread across the Django model class attributes and the
``grant_type``, ``output_type_choices``, ``project_duration_choices`` and
``allocation_home_choices`` modules in nectar-dashboard. The codes are part
of the API contract and must not change.
"""

# Allocation request status --------------------------------------------------

NEW = 'N'
SUBMITTED = 'E'
APPROVED = 'A'
DECLINED = 'R'
UPDATE_PENDING = 'X'
UPDATE_DECLINED = 'J'
DELETED = 'D'

REQUEST_STATUS_CHOICES = (
    # Request created but nothing else
    # User can: Submit
    (NEW, 'New'),
    # Request has been emailed
    # Admin can: Approve, Reject, Edit
    # User can: Edit
    (SUBMITTED, 'Submitted'),
    # Admin has approved the request
    # Admin can: Provision, Edit
    # User can: Amend, Extend
    (APPROVED, 'Approved'),
    # Admin has rejected the request
    # User can: Edit, Submit
    (DECLINED, 'Declined'),
    # User has requested an extension
    # Admin can: Approve, Reject, Edit
    # User can: Edit
    (UPDATE_PENDING, 'Update requested'),
    # Admin has rejected an extension
    # User can: Edit, Extend
    (UPDATE_DECLINED, 'Update declined'),
    # Requests in above status can be viewed by both user
    # and admin at all times.
    # Allocation has been deleted
    (DELETED, 'Deleted'),
)
REQUEST_STATUS_MAP = dict(REQUEST_STATUS_CHOICES)
STATUSES = tuple(REQUEST_STATUS_MAP)

#: Statuses in which a request is awaiting an approver's decision.
PENDING_STATUSES = (SUBMITTED, UPDATE_PENDING)

# Users figure type -----------------------------------------------------------

MEASURED = 'measured'
ESTIMATED = 'estimated'

OPTION_CHOICES = (
    (MEASURED, 'Measured'),
    (ESTIMATED, 'Estimated'),
)

# Sensitive data ---------------------------------------------------------------

NO_SENSITIVE = 'no_sensitive'
SENSITIVE = 'sensitive'
UNKNOWN = 'unknown'

SENSITIVE_DATA_CHOICES = (
    ('', 'Please select...'),
    (NO_SENSITIVE, 'No, the project does not involve sensitive data.'),
    (SENSITIVE, 'Yes, the project involves sensitive data.'),
    (UNKNOWN, 'I am unsure if my project contains sensitive data.'),
)

GREEN = 'green'
YELLOW = 'yellow'
ORANGE = 'orange'
RED = 'red'
NOT_SURE = 'not_sure'

DATA_CLASSIFICATION_CHOICES = (
    ('', 'Please select...'),
    (GREEN, 'Green'),
    (YELLOW, 'Yellow'),
    (ORANGE, 'Orange'),
    (RED, 'Red'),
    (NOT_SURE, 'Not Sure'),
)

YES = 'yes'
NOT_YET = 'not_yet'

INSTITUTIONAL_REVIEW_CHOICES = (
    ('', 'Please select...'),
    (YES, 'Yes'),
    (NOT_YET, 'Not yet'),
)

# Fields of research ----------------------------------------------------------

PERCENTAGE_CHOICES = (
    (0, '0%'),
    (10, '10%'),
    (20, '20%'),
    (30, '30%'),
    (40, '40%'),
    (50, '50%'),
    (60, '60%'),
    (70, '70%'),
    (80, '80%'),
    (90, '90%'),
    (100, '100%'),
)
PERCENTAGES = tuple(p for p, _ in PERCENTAGE_CHOICES)

# Project duration -------------------------------------------------------------

DURATION_CHOICE = (
    (1, "1-month"),
    (3, "3-months"),
    (6, "6-months"),
    (12, "12-months"),
)
DURATIONS = tuple(d for d, _ in DURATION_CHOICE)

# Allocation home --------------------------------------------------------------

ALLOC_HOME_NATIONAL = "national"
ALLOC_HOME_UNASSIGNED = "unassigned"

ALLOC_HOME_CHOICE = (
    ("unassigned", "Unassigned"),
    ("nci", "Australian Capital Territory (NCI)"),
    ("intersect", "New South Wales (Intersect)"),
    ("qcif", "Queensland (QCIF)"),
    ("tpac", "Tasmania (TPAC)"),
    ("uom", "Victoria (Melbourne)"),
    ("monash", "Victoria (Monash)"),
    ("swinburne", "Victoria (Swinburne)"),
    ("auckland", "Auckland Uni (New Zealand)"),
    ("national", "National"),
)

# Resources ----------------------------------------------------------------------

RESOURCE_INTEGER = 'integer'
RESOURCE_BOOLEAN = 'boolean'
RESOURCE_TYPES = (
    (RESOURCE_INTEGER, 'Integer'),
    (RESOURCE_BOOLEAN, 'Boolean'),
)

# Organisations -------------------------------------------------------------------

ORG_ALL_FULL_NAME = "All Organisations"
ORG_ALL_SHORT_NAME = "all"

# Research outputs ------------------------------------------------------------------

PEER_REVIEWED_JOURNAL_ARTICLE = 'AJ'
OTHER_PEER_REVIEWED_PAPER = 'AP'
NON_PEER_REVIEWED_PAPER = 'AN'
BOOK = 'B'
MEDIA_PUBLICATION = 'M'
DATASET = 'D'
SOFTWARE = 'S'
PATENT = 'P'
OTHER = 'O'
UNSPECIFIED = 'U'

OUTPUT_TYPE_CHOICE = (
    (PEER_REVIEWED_JOURNAL_ARTICLE, 'Peer reviewed journal article'),
    (OTHER_PEER_REVIEWED_PAPER, 'Other peer reviewed paper'),
    (NON_PEER_REVIEWED_PAPER, 'Non-peer reviewed paper'),
    (BOOK, 'Book or book chapter'),
    (MEDIA_PUBLICATION, 'Media publication'),  # includes new media
    (DATASET, 'Dataset'),
    (SOFTWARE, 'Software'),
    (PATENT, 'Patent'),
    (OTHER, 'Other'),
    (UNSPECIFIED, 'Unspecified'),  # for legacy cases only
)
OUTPUT_TYPE_MAP = dict(OUTPUT_TYPE_CHOICE)
OUTPUT_TYPES = tuple(OUTPUT_TYPE_MAP)

# Grants ------------------------------------------------------------------------------

GRANT_TYPES = (
    ("arc", "Australian Research Council"),
    ("nhmrc", "NHMRC"),
    ("mrff", "Medical Research Future Fund (MRFF)"),
    ("rdc", "Rural Research and Development Corporations (RDCs)"),
    ("comp", "Other Australian Federal Govt competitive grant"),
    ("govt", "Australian Federal Govt non-competitive funding"),
    ("state", "Australian State / Territory Govt funding"),
    ("industry", "Industry funding"),
    ("ext", "Other external funding"),
    ("inst", "Institutional research funding"),
    ("nz", "New Zealand research funding"),
)
GRANT_TYPE_MAP = dict(GRANT_TYPES)

GRANT_SUBTYPES = (
    # ARC grants from "An overview of ARC grant opportunities"
    # Dec 2020 edition
    ("arc-discovery", "ARC Discovery project"),
    ("arc-indigenous", "ARC Discovery Indigenous"),
    ("arc-decra", "ARC Discovery Early Career Researcher Award"),
    ("arc-future", "ARC Future Fellowship"),
    ("arc-laureate", "ARC Laureate Fellowship"),
    ("arc-itrp", "ARC Industry Transformation Research Program"),
    ("arc-linkage", "ARC Linkage Project"),
    ("arc-coe", "ARC Centre of Excellence"),
    ("arc-lief", "ARC Linkage Infrastructure Equipment and Facilities"),
    ("arc-sri", "ARC Special Research Initiative"),
    # Other schemes from NCRIS reporting form
    ("arc-llasp", "ARC Linkage Learned Academies Special Project"),
    ("arc-other", "Other ARC grant"),
    # NHMRC grants based on
    # https://www.nhmrc.gov.au/funding/new-grant-program/overview
    # in early 2021
    # New schemes
    ("nhmrc-investigator", "NHMRC Investigator grant"),
    ("nhmrc-synergy", "NHMRC Synergy grant"),
    ("nhmrc-ideas", "NHMRC Ideas grant"),
    ("nhmrc-strategic", "NHMRC Strategic or Leverage grant"),
    # Current / earlier schemes from NCRIS reporting form
    ("nhmrc-program", "NHMRC Program grant"),
    ("nhmrc-project", "NHMRC Project grant"),
    ("nhmrc-fas", "NHMRC Fellowship or Scholarship (various)"),
    ("nhmrc-core", "NHMRC Center of Research Excellence"),
    ("nhmrc-development", "NHMRC Development grant"),
    ("nhmrc-equipment", "NHMRC Equipment grant"),
    ("nhmrc-ctcs", "NHMRC Clinical Trial and Cohort Studies grant"),
    ("nhmrc-ics", "NHMRC International Collaborations (various)"),
    ("nhmrc-mrff", "NHMRC Medical Research Future Fund"),
    ("nhmrc-pc", "NHMRC Partnership Centre"),
    ("nhmrc-pp", "NHMRC Partnership project"),
    ("nhmrc-tcr", "NHMRC Targeted Calls for Research"),
    (
        "nhmrc-iriiss",
        "NHMRC Independent Research Institute Infrastructure Support Scheme",
    ),
    ("nhmrc-bdri", "NHMRC Boosting Dementia Research Initiatives (various)"),
    ("nhmrc-other", "Other NHMRC scheme"),
    # MRFF initiatives from the "MRFF Initiative" column of the MRFF
    # grant recipients document (as at 11 June 2026):
    # https://www.health.gov.au/resources/publications/medical-research-future-fund-mrff-grant-recipients
    ("mrff-brain-cancer", "MRFF Australian Brain Cancer Mission"),
    ("mrff-cardiovascular", "MRFF Cardiovascular Health Mission"),
    ("mrff-clinical-trials", "MRFF Clinical Trials Activity"),
    ("mrff-clinician-researchers", "MRFF Clinician Researchers"),
    ("mrff-coronavirus", "MRFF Coronavirus Research Response"),
    ("mrff-dementia-ageing", "MRFF Dementia, Ageing and Aged Care Mission"),
    ("mrff-emcr", "MRFF Early to Mid-Career Researchers"),
    ("mrff-epcdr", "MRFF Emerging Priorities and Consumer Driven Research"),
    ("mrff-frontier", "MRFF Frontier Health and Medical Research"),
    ("mrff-genomics", "MRFF Genomics Health Futures Mission"),
    ("mrff-global-health", "MRFF Global Health"),
    ("mrff-indigenous", "MRFF Indigenous Health Research Fund"),
    ("mrff-commercialisation", "MRFF Medical Research Commercialisation"),
    (
        "mrff-million-minds",
        "MRFF Million Minds Mental Health Research Mission",
    ),
    ("mrff-ncri", "MRFF National Critical Research Infrastructure"),
    ("mrff-preventive", "MRFF Preventive and Public Health Research"),
    ("mrff-primary-care", "MRFF Primary Health Care Research"),
    ("mrff-rart", "MRFF Rapid Applied Research Translation"),
    ("mrff-rdi", "MRFF Research Data Infrastructure"),
    ("mrff-redi", "MRFF Researcher Exchange and Development Within Industry"),
    ("mrff-stem-cell", "MRFF Stem Cell Therapies Mission"),
    ("mrff-tbi", "MRFF Traumatic Brain Injury Mission"),
    ("mrff-other", "Other MRFF initiative"),
    # RDCs
    ("rdc-wa", "Wine Australia"),
    ("rdc-crdc", "Cotton RDC"),
    ("rdc-frdc", "Fisheries RDC"),
    ("rdc-grdc", "Grains RDC"),
    ("rdc-agrifutures", "Rural Industries RDC (AgriFutures Australia)"),
    ("rdc-ael", "Australian Eggs Ltd"),
    ("rdc-livecorp", "Australian Livestock Export Corp Ltd (LiveCorp)"),
    ("rdc-ampc", "Australian Meat Processor Corp"),
    ("rdc-apl", "Australian Pork Ltd"),
    ("rdc-awil", "Australian Wool Innovation Ltd"),
    ("rdc-dal", "Dairy Australia Ltd"),
    ("rdc-fwpa", "Forest and Wood Products Australia"),
    ("rdc-hial", "Horticulture Innovation Australia Ltd"),
    ("rdc-mla", "Meat and Livestock Australia"),
    ("rdc-sral", "Sugar Research Australia Ltd"),
    # States and Territories
    ("act", "Australian Capital Territory Govt funding"),
    ("nsw", "New South Wales Govt funding"),
    ("nt", "Northern Territory Govt funding"),
    ("qld", "Queensland Govt funding"),
    ("sa", "South Australia Govt funding"),
    ("tas", "Tasmania Govt funding"),
    ("vic", "Victoria Govt funding"),
    ("wa", "Western Australia Govt funding"),
    # Unspecified
    ("unspecified", "unspecified"),
)
GRANT_SUBTYPE_MAP = dict(GRANT_SUBTYPES)
