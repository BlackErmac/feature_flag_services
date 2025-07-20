
from dataclasses import dataclass
import random

@dataclass(frozen=False)
class Place:
    row : int
    col : int
    visited : bool
    _type : str 


def create_grid(rows : int , cols : int):
    return [[Place(row, col, False , random.choices(['l', 'w'], weights=[0.4, 0.6])[0]) \
             for col in range(cols)] \
                for row in range(rows)]

def DFS(grid, row, col, visited):
    if (row < 0 or row >= len(grid) or col < 0 or col >= len(grid[0])
            or grid[row][col].visited or grid[row][col]._type == "w"):
        return
    
    grid[row][col].visited = True
    # Explore neighbors (4-directionally)
    DFS(grid, row + 1, col, visited)
    DFS(grid, row - 1, col, visited)
    DFS(grid, row, col + 1, visited)
    DFS(grid, row, col - 1, visited)

def main():
    random_grid = create_grid(5, 5)
    for row in random_grid:
        for place in row:
            print(place._type, end=" ")
        print()

    visited = set()
    for row in range(len(random_grid)):
        for col in range(len(random_grid[0])):
            if random_grid[row][col]._type == "l" and (row, col) not in visited:
                DFS(random_grid, row, col, visited)
                print(f"Island found starting at ({row}, {col})")

if __name__ == "__main__":
    main()
    

