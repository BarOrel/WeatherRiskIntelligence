import { ChangeDetectionStrategy, Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule } from '@angular/material/dialog';

import { HowScoresWork } from '../insights/how-scores-work';

@Component({
  selector: 'app-score-explainer-dialog',
  imports: [MatButtonModule, MatDialogModule, HowScoresWork],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <mat-dialog-content><app-how-scores-work /></mat-dialog-content>
    <mat-dialog-actions align="end"><button mat-flat-button mat-dialog-close>Got it</button></mat-dialog-actions>
  `,
})
export class ScoreExplainerDialog {}
