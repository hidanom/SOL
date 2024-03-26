import math

import numpy as np

from SOL.discrete_bounding import BOUNDING_METHOD_NAME_TO_FUNCTION


class OptimalLinearBounder:
    def __init__(self, target_function, gradient, L1, L2,
                 eps=1e-2, initial_npoints=200, solver='bisect'):
        """
        Instantiates a module that can compute near-optimal linear bounds for the scalar
        function defined by the given arguments.

        Arguments:
        target_function -- a callable function f(x1, x2, ...)
                           The activation function to compute bounds for. This function should
                           return a dReal expression when called with dReal variables, or a concrete
                           value when called with concrete values. See functions.py for examples.

        gradient  --      None, or a list of callable functions [f'_x1(x1, x2, ...), f'_x2(x1, x2, ...), ...]
                      The jacobian of the activation. f'_x1(x1, x2, ...) is the derivate of
                      f with respect to x1, and similarly f1_x2(x1, x2, ...). These functions
                      should take concrete (i.e. float/np floats/torch floats) inputs and
                      return a concrete output. If this
                      argument is None, then the jacobian will be approximated using the
                      finite differences method.
        """
        self.target_function = target_function
        self.gradient = gradient
        self.eps = eps
        self.initial_number_of_points = initial_npoints
        self.L1 = L1
        self.L2 = L2
        assert self.initial_number_of_points > 2
        self.discrete_solver = BOUNDING_METHOD_NAME_TO_FUNCTION.get(solver)
        assert self.discrete_solver is not None, 'Unknown discrete solver'

    @staticmethod
    def _sample_points_regularly(bound, sample_size):
        n = bound.shape[0]
        region_volume = np.prod(bound[:, 1] - bound[:, 0])
        reference_cell_side = (region_volume / sample_size) ** (1. / n)

        grid_arrays = []
        cell_sides = []
        for b in bound:
            num_cells = math.ceil((b[1] - b[0]) / reference_cell_side)
            assert num_cells > 1, 'Not enough points to properly fill the region'
            current_cell_size = (b[1] - b[0]) / num_cells
            cell_sides.append(current_cell_size)

            grid_arrays.append(np.linspace(
                b[0] + current_cell_size / 2,
                b[1] - current_cell_size / 2,
                num_cells))

        points =  np.array(list(map(lambda a: a.flatten(), np.meshgrid(*grid_arrays))))
        points = np.transpose(points, axes=(1, 0))
        cell_sides = np.array(cell_sides)

        cell_diam = np.linalg.norm(cell_sides)
        side_to_diam_ratio = cell_sides / cell_diam
        return points, cell_diam * np.ones((points.shape[0],)), side_to_diam_ratio
    
    @staticmethod
    def _get_G_bound(bound):
        assert bound.shape[0] == 1, 'Bounding G for dim > 1 is not implemented'
        return 1.

    def _find_discrete_upper_bound(self, bound, points, values):
        center = bound.mean(axis=-1)
        points_shifted = points - center

        result = self.discrete_solver(points_shifted, values, self.eps)
        result[-1] -= (result[:-1] * center).sum()
        return result

    def _bound_one_side(self, bound, upper=True):
        G = self._get_G_bound(bound)
        points, cell_diams, side_to_diam_ratio = self._sample_points_regularly(
            bound, self.initial_number_of_points)
        points = points.T

        point_act = self.target_function(*points)
        point_grad = self.gradient(*points).T
        if not upper:
            point_act *= -1
            point_grad *= -1

        assert points.shape[1] > bound.shape[0], 'Need at least dim + 1 point'

        # [coords, num_subcubes]
        subcube_offsets = np.array(
            [
                [
                    1 if subcube_mask & (1 << dim) else -1 
                    for dim in range(len(bound))
                ] for subcube_mask in range(1 << len(bound))
            ]
        ).T
        offset_to_diam_ratio = 0.25 * side_to_diam_ratio
        
        while True:
            coeffs = self._find_discrete_upper_bound(bound, points.T, point_act)
            lin_grad = coeffs[:-1]

            bound_diff = np.matmul(lin_grad, points) + coeffs[-1] - point_act

            diffs = (1 + G) * self.L1 * (cell_diams / 2)
            diffs -= bound_diff

            diffs2 = np.linalg.norm(
                np.expand_dims(lin_grad, axis=-1) - point_grad, axis=0) * (cell_diams / 2)
            diffs2 += 0.5 * self.L2 * (cell_diams / 2) ** 2
            diffs2 -= bound_diff
            
            min_diffs = np.minimum(diffs, diffs2)
            holds = min_diffs < self.eps

            if np.all(holds):
                coeffs[-1] += np.max(min_diffs)
                if not upper:
                    coeffs *= -1
                return coeffs

            keep_points = points[:, holds]
            keep_cell_diams = cell_diams[holds]
            keep_point_act = point_act[holds]
            keep_point_grad = point_grad[:, holds]
            
            # [coords, n]
            split_points = points[:, ~holds]
            # [n]
            split_cell_diams = cell_diams[~holds]
            
            # [coords, num_subcubes, n]
            offsets = np.expand_dims(subcube_offsets, axis=-1) * split_cell_diams
            offsets *= offset_to_diam_ratio.reshape([-1, 1, 1])
            new_points = np.expand_dims(split_points, axis=1) + offsets
            new_cell_diams = np.tile(
                np.expand_dims(split_cell_diams, axis=0), reps=[new_points.shape[-2], 1])
            new_cell_diams /= 2
            

            num_coords = bound.shape[0]
            new_points = np.reshape(new_points, [num_coords, -1])
            # new_points = np.stack(
            #     [np.clip(coords, a_min=l, a_max=u) for coords, (l, u) in zip(new_points, bound)])
            new_cell_diams = np.reshape(new_cell_diams, [-1])

            new_point_act = self.target_function(*new_points)
            new_point_grad = self.gradient(*new_points).T
            if not upper:
                new_point_act *= -1
                new_point_grad *= -1

            points = np.concatenate([keep_points, new_points], axis=-1)
            cell_diams = np.concatenate([keep_cell_diams, new_cell_diams], axis=-1)
            point_act = np.concatenate([keep_point_act, new_point_act], axis=-1)
            point_grad = np.concatenate([keep_point_grad, new_point_grad], axis=-1)

    def find_optimal_bounds(self, bound):
        """
        Compute linear lower and upper bounds for the target function over the
        input region defined by bound.
        
        Arguments:
        bound -- [(lb1, ub1), (lb2, ub2), ...]
                 The input region of the activation function. (lb1, ub1) is the interval
                 for the first input, (lb2, ub2) is the interval for the second input,
                 and so on...

        Returns: [(cl1, cl2, ...), (cu1, cu2, ...)]
                 lower/upper bound coefficients that form sound linear lower/upper bounds
                 over the input region defined by bound
        """

        assert all([b[1] - b[0] > -1e-5 for b in bound]), 'Bounds must have positive width'

        return (
            self._bound_one_side(bound, upper=False),
            self._bound_one_side(bound, upper=True)
        )