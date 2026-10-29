export const SAMPLE_TEXT = String.raw`\section{Introduction}

Medical image segmentation is a important task in computer-aided diagnosis, because it allows clinicians to delineate organs and lesions in a precise way~\cite{ronneberger2015unet,chen2021transunet}. However, existing methods uses a lot of computation, which may limit their deployment on edge devices.

In this work, we propose a lightweight decoder that combines multi-scale attention with depth-wise convolutions. The training objective is the weighted sum $\mathcal{L} = \lambda_1 \mathcal{L}_{\text{Dice}} + \lambda_2 \mathcal{L}_{\text{CE}}$, where we set $\lambda_1 = 0.7$ as described in Section~\ref{sec:method}.

\begin{equation}
  \mathcal{L}_{\text{Dice}} = 1 - \frac{2 \sum_i p_i g_i}{\sum_i p_i + \sum_i g_i}
  \label{eq:dice}
\end{equation}

Experiments on the Synapse dataset shows that our model reaches a mean Dice score of 83.6\% with only 3.9M parameters, which suggests that accuracy does not necessarily require a big network.`;
