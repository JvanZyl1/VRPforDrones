## DRONES AND TRUCKS ##

#NOTE: this doesnt work as were using old truck model, need to update to new model (see Truck_Only.ipynb for working truck model)


from gurobipy import Model,GRB,LinExpr,quicksum
import numpy as np
from scipy.spatial import distance
import os
import socket
from load_dataset import Dataset

'''
# For Ugo's laptop (only needed for jupy notebooks)
# Define the node name or another identifier of your laptop
my_laptop_node = 'Ugos-MacBook-Pro.local'

# Get the current system's node name using socket.gethostname()
current_node = socket.gethostname()

if current_node == my_laptop_node:
    # Set the environment variable for Gurobi license file
    os.environ["GRB_LICENSE_FILE"] = "/Users/ugomunzi/gurobi/licenses/gurobi.lic"
    print("Gurobi license path set for Ugo's MacBook Pro.")
else:
    print("Not Ugo's MacBook Pro, using default or no specific license settings.")
'''

## MODEL PARAMETERS ##
W_T = 1500 #empty weight truck [kg]
Q_T = 1000 #load capacity of trucks [kg]
W_D = 25 #empty weight drone [kg]
Q_D = 5 #load capacity of drones [kg]
C_T = 25 #travel cost of trucks per unit distance [monetary unit/km]
C_D = 1 #travel cost of drones per unit distance [monetary unit/km]
C_B = 500 #basis cost of using a truck equipped with a drone [monetary unit]
E = 0.5 #maximum endurance of empty drones [hours]
S_T = 60 #average travel speed of the trucks [km/h]
S_D = 65 #average travel speed of the drones [km/h]
M = 500 #BigM constant

## FUNCTIONS ##
def get_manhattan_distance(data):
    """
    Returns a dictionary with manhattan distances between all nodes in dataset
    """
    distance_dict = {}
    for node1 in data.keys():
        for node2 in data.keys():
            distance_dict[node1, node2] = distance.cityblock([data[node1]['X'], data[node1]['Y']], [data[node2]['X'], data[node2]['Y']])
    return distance_dict

def get_euclidean_distance(data):
    """
    Returns a dictionary with euclidean distances between all nodes in dataset
    """
    distance_dict = {}
    for node1 in data.keys():
        for node2 in data.keys():
            distance_dict[node1, node2] = distance.euclidean([data[node1]['X'], data[node1]['Y']], [data[node2]['X'], data[node2]['Y']])
    return distance_dict

def get_time_dict(data, avg_speed, distance_dict):
    """
    Returns a dictionary with travel times between all nodes in dataset
    """
    time_dict = {}
    for node1 in data.keys():
        for node2 in data.keys():
            time_dict[node1, node2] = distance_dict[node1, node2] / avg_speed
    return time_dict


## LOAD DATASET ##
current_dir = os.getcwd()
# Select which data folder to use
data_subfolder = '0.3'
data_subfoldercopy = '0.3_copy'
data_num_nodes = '40'
data_area = '20'

data_file_name = f'{data_num_nodes}_{data_area}_{data_subfoldercopy}'
dataset_path = f'dataset/{data_subfolder}/{data_file_name}.txt'
output_file_path = os.path.join(current_dir, data_file_name + '_solution.sol')#used to save solution file

dataset = Dataset(dataset_path)

## PRE-PROCESSING ##

num_trucks = 10 # set to high number, optimiser will decide how many truck to use
truck_distance_dict = get_manhattan_distance(dataset.data)
drone_distance_dict = get_euclidean_distance(dataset.data)
truck_time_dict = get_time_dict(dataset.data, S_T, truck_distance_dict)
drone_time_dict = get_time_dict(dataset.data, S_D, drone_distance_dict)

print(truck_distance_dict)

#definitions of N_0, N and N_plus follow from paper
N = list(dataset.data.keys()) #set of nodes with depot at start
N_customers = N.copy()
N_customers.remove('D0')
Tr = [f'Tr{i}' for i in range(1, num_trucks+1)] #set of trucks

num_drones = num_trucks
# V is the set of vehicles, which includes the trucks and the drones
Dr = [f'Dr{i}' for i in range(1, num_drones+1)] #set of drones
V = Tr + Dr
print(Tr)

## DEFINE MODEL ##

# Create a new model
model = Model("Truck_Routing")

# Define decision variables
x = model.addVars(Tr, [(i, j) for i in N for j in N if i != j], lb=0, ub=1, vtype=GRB.BINARY, name='x')
y = model.addVars(V, lb=0, ub=1, vtype=GRB.BINARY, name='y')
t = model.addVars(V, N, lb=0, vtype=GRB.CONTINUOUS, name='t')
t_max = model.addVar(lb=0, vtype=GRB.CONTINUOUS, name='t_max') #used for the minimising the max delivery time (find max time of all trucks, not each individual truck)
# Make one for the drones as well
# [v, i, j, k] -> vehicle, node_from, node_to, node_retrieve
# Initialize an empty dictionary to hold the decision variables
d = model.addVars(Dr, [(i, j, k) for i in N for j in N for k in N if i != j and i != k and j != k], lb=0, ub=1, vtype=GRB.BINARY, name='d')
"""
d = {}
# Loop over each drone
for drone in Dr:
    # Loop over each node
    for node in N:
        # Loop over each node again
        for customer in N:
            # Skip if the first node is the same as the second node
            if node != customer:
                # Loop over each node again
                for retrival in N:
                    # Skip if the first node is the same as the third node or the second node is the same as the third node
                    if retrival != node and retrival != customer:
                        # Add a binary decision variable to the dictionary
                        d[drone, node, customer, retrival] = model.addVar(lb=0, ub=1, vtype=GRB.BINARY, name=f'd_{drone}_{node}_{customer}_{retrival}')
"""

# Objective 1: Cost both due to transportation and base cost of using truck if active)
cost_obj = quicksum(C_T * truck_distance_dict[i,j] * x[truck,i,j] for i in N for j in N if i != j for truck in Tr) + \
           quicksum(C_B * y[truck] for truck in Tr) + \
           quicksum(C_D * (drone_distance_dict[i,j] + drone_distance_dict[j,k]) * d[drone,i,j,k] for i in N for j in N for k in N if i != j if i != k if j != k for drone in Dr)
# Objective 2: environmental_obj is distance[i,j] * Weight* x[v,i,j] for all v,i,j (i.e. energy consumption)
environmental_obj = quicksum(truck_distance_dict[i,j] * W_T * x[truck,i,j] for i in N for j in N if i != j for truck in Tr)
# Objective 3: minimise max delivery time for each truck
time_obj = t_max

# Objective function (minimize cost both due to transportation and base cost of using truck if active)
cost_obj = quicksum(C_T * truck_distance_dict[i,j] * x[truck,i,j] for i in N for j in N if i != j for truck in Tr) + quicksum(C_B * y[v] for v in V)

obj = cost_obj + environmental_obj + time_obj
model.setObjective(obj, GRB.MINIMIZE)

model.update()


# Constraint 1: Each customer is visited by exactly one truck or drone

# Each customer is visited by exactly one vehicle
constraints = {}
# Loop over each customer
for customer in N_customers:
    # Initialize the sum for the current customer
    sum_for_current_customer = 0

    # Loop over each truck
    for truck in Tr:
        # Loop over each node
        for node in N:
            # Skip if customer is equal to node
            if customer != node:
                # Add the variable to the sum
                sum_for_current_customer += x[truck, node, customer]

    # Loop over each drone
    for drone in Dr:
        # Loop over each node
        for node in N:
            # Skip if customer is equal to node
            if customer != node:
                # Loop over each retrieval node
                for retireval in N:
                    # Skip if retrieval is equal to node or customer
                    if retireval != node and retireval != customer:
                        # Add the variable to the sum
                        sum_for_current_customer += d[drone, node, customer, retireval]

    # The sum for the current customer must be equal to 1
    constraints[customer] = model.addConstr(sum_for_current_customer == 1, name=f'Customer_{customer}_visited_once')

# Constraint 2: Each depot must be visited exactly once

# Each truck must leave the depot
# y - active
# 'D0' - depot
# Loop over each truck
for truck in Tr:
    sum_for_current_vehicle = quicksum(x[truck, 'D0', customer] for customer in N_customers)
    model.addConstr(sum_for_current_vehicle == y[truck], name=f'Truck_leaves_depot_{truck}')


# Constraint 3: Each truck arrives at depot if active : TRUCKS

# Each truck must return to the depot
# Loop over each truck
for truck in Tr:
    sum_for_current_vehicle = quicksum(x[truck, customer, 'D0'] for customer in N_customers)
    model.addConstr(sum_for_current_vehicle == y[truck], name=f'Truck_returns_to_depot_{truck}')


# Constraint 4: If a truck arrives at a customer node it must also leave

# If a truck visits a customer, it must leave the customer
for truck in Tr:
    for node in N_customers:
        model.addConstr(
            quicksum(x[truck, node, j] for j in N if j != node) == 
            quicksum(x[truck, j, node] for j in N if j != node),
            name=f'Flow_balance_{truck}_{node}'
        )
'''
#Constraint 5: Time at a node is equal or larger than time at previous nodes plus travel time (or irrelevant). Eliminates need for subtour constraints.
# Define a large constant M for the big-M method : TRUCKS
'''
M_subtour = 60000000  # Make sure M is larger than the maximum possible travel time

# Add time constraints for all vehicles, nodes, and customers
for truck in Tr:
    for node in N:
        for customer in N:
            if node != customer:
                model.addConstr(
                    t[truck, customer] >= t[truck, node] + truck_time_dict[(node, customer)] - M_subtour * (1 - x[truck, node, customer]),
                    name=f'Time_{truck}_{node}_{customer}'
                )

# Constraint 6: Payloads : TRUCKS

# The total payload delivered to the customer must be less or equal to the truck load capacity Q_T
for truck in Tr:
    model.addConstr(quicksum(dataset.data[i]['Demand'] * x[truck, i, j] for i in N for j in N if i != j) <= Q_T, 
                    name=f'Payload_{truck}')

# Constraint 7: Link y variable to x variable : TRUCKS
#if any link in x (for each truck) is active -> y = 1
# can do this by checking if each truck leaves the depot (all trucks must leave depot if active)

for truck in Tr:
    model.addConstr(y[truck] == quicksum(x[truck, 'D0', i] for i in N_customers), name=f'Link_y{truck}_to_x_{truck}')

# Constraint 8: Update time variable : TRUCKS
# Loop over each truck
for truck in Tr:
    # Loop over each customer
    for customer in N_customers:
        # Initialize the sum for the current customer
        sum_for_current_customer = 0

        # Loop over each node
        for node in N:
            # Skip the current customer
            if node != customer:
                # Add the time at which the truck leaves the node plus the travel time from the node to the customer,
                # multiplied by the decision variable indicating whether the truck travels from the node to the customer,
                # to the sum for the current customer
                sum_for_current_customer += (t[truck, node] + truck_time_dict[(node, customer)]) * x[truck, node, customer]

        # Add a constraint to the model that the time at which the truck arrives at the customer is equal to the sum for the current customer
        model.addConstr(t[truck, customer] == sum_for_current_customer, name=f'Update_time_{truck}_{customer}')


# Constraint 9: Update max delivery time variable
for truck in Tr:
    for customer in N_customers:
        # Add a constraint to the model that the maximum delivery time is greater than or equal to the delivery time to the customer for each vehicle
        model.addConstr(t_max >= t[truck, customer], name=f'Update_max_delivery_time_{truck}_{customer}')

# Constraint 10: Ensures each drone is launched at most once at all customer and depot nodes
for drone in Dr:
    for node in N:
        for customer in N:
            if node != customer:
                sum_for_current_customer = 0
                for retireval in N:
                    if retireval != node and retireval != customer:
                        sum_for_current_customer += d.get((drone, node, customer, retireval), 0)
                model.addConstr(sum_for_current_customer <= 1, name=f'Drone_launched_{drone}_{node}_{customer}')
    
# Constraint 11: Ensures each drone is retrieved at most once at all customer and depot nodes.

for drone in Dr:
    for node in N:
        for customer in N:
            if node != customer:
                sum_for_current_customer = 0
                for retireval in N:
                    if retireval != node and retireval != customer:
                        sum_for_current_customer += d.get((drone, retireval, customer, node), 0)
                model.addConstr(sum_for_current_customer <= 1, name=f'Drone_retrieved_{drone}_{node}_{customer}')

# Constraint 12: Ensures drones are not loaded beyond its load capacity during flight.

# Loop over each drone
for drone in Dr:
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Initialize the sum for the current customer
                sum_for_current_customer = 0

                # Loop over each node
                for i in N:
                    # Get the decision variable for the current drone, node, i, and customer
                    decision_variable = d.get((drone, node, i, customer), 0)

                    # Multiply the demand of node i by the decision variable and add it to the sum for the current customer
                    sum_for_current_customer += dataset.data[i]['Demand'] * decision_variable

                # Add a constraint to the model that the sum for the current customer is less than or equal to the drone's capacity
                model.addConstr(sum_for_current_customer <= Q_D, name=f'Drone_payload_{drone}_{node}_{customer}')

# Constraint 13: Ensures that if drone is launched at node i and retrieved at node k,
# the truck must also pass through both nodes to launch/retrieve the drone.

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N_customers:
            # Skip if the node is the same as the customer
            if node != customer:
                #Loop over each retrieval node
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # If d[drone, node, customer, retireval] is active, then x[truck, node, retireval]must be active
                        model.addConstr(d[drone, node, customer, retireval] <= x[truck, node, retireval], name=f'Drone_launched_retrieved_{drone}_{node}_{customer}_{retireval}')
                    
    i += 1

# Constraint 14: Ensures delivery sequence of trucks is consistent with that of the drones
# (GPT: "This constraint ensures that if a drone is deployed for a mission from node i to j and retrieved at node k,
# the truck must visit node i before node k. Essentially, it ties the truck's routing to the drone's operations,
# ensuring that the sequence of visits is logically consistent with the drone's deployment and retrieval.").

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(t[truck, retireval] >= t[truck, node] - M_subtour * (1 - d[drone, node, customer, retireval]), name=f'Drone_delivery_sequence_{drone}_{node}_{customer}_{retireval}')
                        #model.addConstr(t[truck, retireval] >= 0, name=f'Drone_delivery_sequence_{drone}_{node}_{customer}_{retireval}_time')
    i += 1


# Constraint 15: Launch time of drone at node i cannot be earlier than arrival time of the truck at same node
# unless drone is not launched at node i (big M constant negates this constraint in this case)

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(
                            t[drone, node] >= t[truck, node] - M_subtour * (1 - d[drone, node, customer, retireval]),
                            name=f'Drone_launch_time_greater_{drone}_{node}_{customer}_{retireval}'
                        )
    i += 1

"""
# Constraint 16: Launch time of drone at node i cannot be later than arrival time of the truck at same node
# unless drone is not launched at node i (big M constant negates this constraint in this case)

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(
                            t[drone, node] <= t[truck, node] - M * (1 - d[drone, node, customer, retireval]),
                            name=f'Drone_launch_time_less_{drone}_{node}_{customer}_{retireval}'
                        )
    i += 1
"""

# Constraint 17: Ensures drone retrieval time at node k is not earlier than truck's arrival at that node.
# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(
                            t[drone, retireval] >= t[truck, retireval] - M_subtour * (1 - d[drone, node, customer, retireval]),
                            name=f'Drone_retrieval_time_{drone}_{node}_{customer}_{retireval}'
                        )
    i += 1

"""
# Constraint 18: Ensures drone retrieval time at node k is not later than truck's arrival at that node.
# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(t[truck, retireval] <= t[truck, node] + M * (1 - d[drone, node, customer, retireval]), name=f'Drone_retrieval_time_{drone}_{node}_{customer}_{retireval}')
    i += 1
"""


# Constraint 19: Ensures arrival time of drone at node j "customer" is after departure (launch) time from node i "base" based on
# euclidean distance dijE. Big M deactivates constraint if drone doesnt make direct trip between the two nodes.

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(
                            t[drone, customer] >= t[drone, node] + drone_time_dict[(node, customer)] - M_subtour * (1 - d[drone, node, customer, retireval]),
                            name=f'Drone_arrival_time_{drone}_{node}_{customer}_{retireval}')
    i += 1

# Constraint 20: Ensures that the time of retrieval at node k occurs after the time of delivery of the drone at node j
# based on euclidean distance dijE. Big M deactivates constraint if drone doesnt make direct trip between the two nodes.

# Loop over each drone
i = 0
for drone in Dr:
    truck = Tr[i]
    # Loop over each node
    for node in N:
        # Loop over each customer
        for customer in N:
            # Skip if the node is the same as the customer
            if node != customer:
                # Loop over each node again
                for retireval in N:
                    # Skip if the node is the same as the customer or the retrieval node
                    if retireval != node and retireval != customer:
                        # Add a constraint to the model that the decision variable for the current drone, node, customer, and retrieval node
                        # is less than or equal to the decision variable for the current drone, node, and customer
                        # And t[truck,retireval] cannot equal 0
                        model.addConstr(
                            t[drone, retireval] >= t[drone, customer] + drone_time_dict[(customer, retireval)] - M_subtour * (1 - d[drone, node, customer, retireval]),
                            name=f'Drone_retrieval_time_{drone}_{node}_{customer}_{retireval}'
                        )
    i += 1


# Constraint 21: Ensures total flight time of drone is less than its maximum endurance.
# Big M deactivates constraint if drone doesnt make direct trip between the two nodes.


# Constraint 22: If a truck is active, the corresponding drone is also active (link y[truck] to corresponding y[drone])

# Loop over each vehicle
for vehicle in V:
    # If the vehicle is a truck
    if 'T' in vehicle:
        # Get the corresponding drone
        drone = 'D' + vehicle[1:]
        # Add the constraint
        model.addConstr(y[vehicle] <= y[drone], name=f'Active_truck_implies_active_drone_{vehicle}')
## SOLVE MODEL ##

# Update the model to integrate constraints
model.update()

# Write model to a file
model.write('TruckonlySimple.lp')

# Tune solver parameters
#model.tune()

# Optimize the model
model.optimize()

# Print the results
if model.status == GRB.OPTIMAL:
    print('Optimal objective: %g' % model.objVal)
    for v in model.getVars():
        if v.x > 0:
            print('%s: %g' % (v.varName, v.x))
else:
    print('Optimization was stopped with status %d' % model.status)


## POST-PROCESSING ##

# Extract and store the solution
solution = {var.varName: var.x for var in model.getVars()}
"""
# Print all routes for each vehicle
for vehicle in V:
    #print active vehicle (y)
    var_name_y = f'y[{vehicle}]'
    if solution.get(var_name_y, 0) >= 0.99:
        print(f'Vehicle {vehicle} is active')
    total_payload = 0
    for node_from in N:
        for node_to in N:
            if node_from != node_to:
                #print active links
                var_name_x = f'x[{vehicle},{node_from},{node_to}]'
                if solution.get(var_name_x, 0) >= 0.99:
                    print(f'{node_from} -> {node_to} by truck')
                    total_payload += dataset.data.get(node_from, {}).get('Demand', 0)
                #print active drone links
                for node_drone in N:
                    if node_drone != node_from and node_drone != node_to:
                        var_name_d = f'd[{vehicle},{node_from},{node_to},{node_drone}]'
                        if solution.get(var_name_d, 0) >= 0.99:
                            print(f'{node_from} -> {node_to} via {node_drone} by drone')
                            total_payload += dataset.data.get(node_from, {}).get('Demand', 0)
    print()
    print(f'Total payload delivered by vehicle {vehicle}: {total_payload}\n')
"""

# Old post-processing

#exctract active vehicles
active_vehicles = [v for v in V if solution[f'y[{v}]'] >= 0.99]

# Extract routes
active_routes_truck = {}
active_routes_drone = {}
for v in active_vehicles:
    if 'T' in v:
        active_routes_truck[v] = []
    else:
        active_routes_drone[v] = []
    for node_from in N:
        for node_to in N:
            if node_from != node_to:
                # Check if the vehicle is a truck or a drone
                if 'T' in v:
                    # If it's a truck, use the 'x' variable
                    if solution.get(f'x[{v},{node_from},{node_to}]', 0) >= 0.99:
                        active_routes_truck[v].append((node_from, node_to))
                else:
                    # If it's a drone, use the 'd' variable
                    for retireval in N:
                        if retireval != node_from and retireval != node_to:
                            if solution.get(f'd[{v},{node_from},{node_to},{retireval}]', 0) >= 0.99:
                                active_routes_drone[v].append((node_from, node_to, retireval))

print('active routes for trucks', active_routes_truck)
print('active routes for drones', active_routes_drone)
                
"""
#retrieve timestamps of customer visits
timestamps = {}
for v in active_vehicles:
    timestamps[v] = {}
    for node in active_routes[v]:  # Only consider nodes that the vehicle travels to
        timestamps[v][node] = solution[f't[{v},{node}]']

print('\n')
print('timestamps', timestamps)

#print all solution variables which have value of 1
dataset.plot_data(show_demand=False, scale_nodes=True, show_labels=True, active_routes=active_routes)
"""
