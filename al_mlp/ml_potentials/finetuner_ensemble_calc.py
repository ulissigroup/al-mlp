from al_mlp.ml_potentials.finetuner_calc import FinetunerCalc
from al_mlp.ml_potentials.finetuner_gemnet_calc import GemnetFinetunerCalc
from al_mlp.ml_potentials.finetuner_spinconv_calc import SpinconvFinetunerCalc
from al_mlp.ml_potentials.finetuner_dimenetpp_calc import DimenetppFinetunerCalc
import numpy as np


class FinetunerEnsembleCalc(FinetunerCalc):
    """
    FinetunerEnsembleCalc.
    ML potential calculator class that implements an ensemble of partially frozen ocp models.

    Parameters
    ----------
    model_classes: list[str]
        list of paths to classnames, corresponding to checkpoints and configs, e.g.
        [
            "Gemnet",
            "Spinconv",
            "Dimenetpp",
        ]

    model_paths: list[str]
        list of paths to model configs, corresponding to classes list, e.g.
        [
            '/home/jovyan/working/ocp/configs/s2ef/all/gemnet/gemnet-dT.yml',
            '/home/jovyan/working/ocp/configs/s2ef/all/spinconv/spinconv_force.yml',
            '/home/jovyan/working/ocp/configs/s2ef/all/dimenet_plus_plus/dpp_forceonly.yml',
        ]

    checkpoint_paths: list[str]
        list of paths checkpoints, corresponding to classes list, e.g.
        [
            '/home/jovyan/shared-datasets/OC20/checkpoints/s2ef/gemnet_t_direct_h512_all.pt'
            '/home/jovyan/shared-datasets/OC20/checkpoints/s2ef/spinconv_force_centric_all.pt',
            '/home/jovyan/shared-datasets/OC20/checkpoints/s2ef/dimenetpp_all_forceonly.pt',
        ]

    mlp_params: dict
        dictionary of parameters to be passed to be used for initialization of the model/calculator
    """

    def __init__(
        self,
        model_classes: "list[str]",
        model_paths: "list[str]",
        checkpoint_paths: "list[str]",
        mlp_params: dict = {},
    ) -> None:

        self.model_classes = model_classes
        self.model_paths = model_paths
        self.checkpoint_paths = checkpoint_paths

        self.finetuner_calcs = []
        for i in range(len(self.model_classes)):
            if self.model_classes[i] == "Gemnet":
                finetuner = GemnetFinetunerCalc
            elif self.model_classes[i] == "Spinconv":
                finetuner = SpinconvFinetunerCalc
            elif self.model_classes[i] == "Dimenetpp":
                finetuner = DimenetppFinetunerCalc

            self.finetuner_calcs.append(
                finetuner(
                    model_path=self.model_paths[i],
                    checkpoint_path=self.checkpoint_paths[i],
                    mlp_params=mlp_params,
                )
            )

        FinetunerCalc.__init__(self, mlp_params=mlp_params)

    def init_model(self):
        self.model_class = "Ensemble"
        self.ml_model = True

        for finetuner in self.finetuner_calcs:
            finetuner.init_model()

    def train_ocp(self, dataset):
        for finetuner in self.finetuner_calcs:
            self.ocp_calc = finetuner.ocp_calc
            train_loader = self.get_data_from_atoms(dataset)
            finetuner.ocp_calc.trainer.train_loader = train_loader
            finetuner.ocp_calc.trainer.train()

    def calculate_ml(self, atoms, properties, system_changes) -> tuple:
        """
        Give ml model the ocp_descriptor to calculate properties : energy, forces, uncertainties.

        Args:
            ocp_descriptor: list object containing the descriptor of the atoms object

        Returns:
            tuple: (energy, forces, energy_uncertainty, force_uncertainties)
        """
        energy_list = []
        forces_list = []
        for finetuner in self.finetuner_calcs:
            finetuner.ocp_calc.calculate(atoms, properties, system_changes)
            energy_list.append(finetuner.ocp_calc.results["energy"])
            forces_list.append(finetuner.ocp_calc.results["forces"])

        e_mean = np.mean(energy_list)
        f_mean = np.mean(forces_list, axis=0)

        self.train_counter += 1
        e_std = np.std(energy_list)
        f_stds = np.std(forces_list, axis=0)

        f_std = np.average(f_stds).item()

        return e_mean, f_mean, e_std, f_std