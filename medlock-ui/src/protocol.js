// Medication protocol for the Pregnyl trigger shot.
// Kept as data so the clinic can configure other medications later
// without touching the screen code.
//
// NOTE: placeholder steps for a simulated training prototype.
// Confirm the real sequence and volumes with your clinician contact.

export const PROTOCOL = {
  medication: 'Pregnyl trigger shot',
  targetVolumeMl: 1.0,
  supplies: [
    { id: 'diluent', label: 'Diluent vial' },
    { id: 'powder', label: 'Powder vial' },
    { id: 'syringe', label: 'Syringe' },
    { id: 'needle', label: 'Needle' },
    { id: 'wipes', label: 'Alcohol wipes' },
  ],
  prepSteps: [
    { id: 'wipe', title: 'Wipe both vial tops', detail: 'Use one alcohol wipe for each vial. Let them dry.' },
    { id: 'draw-diluent', title: 'Draw 1 mL of diluent into the syringe', detail: 'Pull the plunger slowly to the 1 mL line.' },
    { id: 'inject-powder', title: 'Inject the diluent into the powder vial', detail: 'Aim at the side of the vial, not straight at the powder.' },
    { id: 'swirl', title: 'Swirl gently to dissolve', detail: 'The liquid should be clear with no flakes.', warning: 'Do not shake the vial.' },
    { id: 'draw-dose', title: 'Draw up the full dose', detail: 'Turn the vial upside down and pull to your dose line.' },
  ],
}
