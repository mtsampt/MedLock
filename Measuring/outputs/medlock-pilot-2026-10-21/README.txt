MEDLOCK PILOT IMAGE REVIEW

27 original photographs were copied byte-for-byte into images/001.JPG through images/027.JPG.
Original source files on the Desktop were not renamed or modified. Original filenames and SHA-256 hashes are in labels.csv and manifest.json.
Order follows ascending original filename and agrees with EXIF capture chronology.

LABELS
yes: a distinct air-pocket/bubble outline is visible.
no: no confidently identifiable air pocket is visible. This does not establish absence of microscopic or hidden air.
uncertain: features may be bubbles, surface droplets, or reflections. Exclude these from binary supervised labels until reviewed or replaced.
Labels are provisional annotations. Photos 010-012 and 019-021 were changed from uncertain to no on user confirmation. Previous observations and label provenance are preserved in manifest.json and labels.csv. No label establishes absence of hidden/microscopic air.
No air/liquid volumes were inferred from appearance or the intended sequence.
No segmentation masks have been created.

GROUPING
P01-P09 are inferred from consecutive triplets under the user's stated ordering and previous collection plan. Actual preparation changes have not been independently confirmed.
All files belong to the same observed collection session S01. Physical syringe identity is unknown.
Keep this pilot together when later evaluating on independent sessions/syringes. Do not randomly divide its photos into training and test sets.
For stricter grouping, the same starting fill may persist across triplets, and all images may use one syringe.

QUALITY FINDINGS
Large air pockets are visible. Tiny bright features are less conclusive.
The camera views the syringe vertically; the intended device drawing places it horizontally. Gravity changes bubble position and shape.
Cardboard folds and the tabletop boundary refract through the barrel and could mimic fluid boundaries. Replace with a smooth, uniformly illuminated diffuser for the next collection.
Warm lighting, reflections, and partially rotated markings limit small-bubble assessment.
Current labels: 18 yes, 9 no, 0 uncertain. The small, single-session pilot is insufficient for a reliable training/evaluation claim.
Collect new no-visible-air examples at all fill levels and small-bubble examples, with an improved smooth background. Use the final horizontal device orientation if that is the team's intended orientation.

FILES
labels.xlsx: readable review table and formula-linked label counts.
labels.csv: machine-readable per-image metadata and labels.
manifest.json: same records, including hashes and missing reference measurements as null.
review/contact_01.jpg through contact_03.jpg: inspection crops with review labels. These are review derivatives, not replacement training images.
images/: full-resolution original-byte copies. Apply EXIF orientation when loading for a model.
