! Copyright 2023 Canonical Ltd.
! See LICENSE file for licensing details.

program hpcsee
    implicit none

    ! Declare types
    integer :: i, j
    real :: c_minotaur, c_manatee, c_macaw, c_barracuda
    character(len=100) :: filename
    type :: record
        character(len=80) :: email
        character(len=80) :: country
        character(len=30) :: vote
    end type record
    type(record), dimension(150) :: votes

    ! Identify target dataset
    if(command_argument_count().ne.1) then
        write(*,*) "Error: Please specify CSV dataset file."
        stop
    end if
    call get_command_argument(1, filename)

    ! Read dataset
    open(unit=10, file=filename, status="old")
    do i=1, 150
        read(10, *) votes(i)
    end do
    close(unit=10)

    ! Calculate probability
    c_minotaur = 0
    c_manatee = 0
    c_macaw = 0
    c_barracuda = 0
    do i=1, 150
        select case (votes(i)%vote)
            case ("Mantic Minotaur")
                c_minotaur = c_minotaur + 1
            case ("Mantic Manatee")
                c_manatee = c_manatee + 1
            case ("Mantic Macaw")
                c_macaw = c_macaw + 1
            case ("Boisterous Barracuda")
                c_barracuda = c_barracuda + 1
        end select
    end do

    print *, "Probability of the next Ubuntu release name being..."
    print "(1x, a, 8x, i2, a)", "Mantic Minotaur:", nint((c_minotaur / 150) * 100), "%"
    print "(1x, a, 9x, i2, a)", "Mantic Manatee:", nint((c_manatee / 150) * 100), "%"
    print "(1x, a, 11x, i2, a)", "Mantic Macaw:", nint((c_macaw / 150) * 100), "%"
    print "(1x, a, 3x, i2, a)", "Boisterous Barracuda:", nint((c_barracuda / 150) * 100), "%"
    print *, ""
    print *, "Generating what mascot might look like..."

end program hpcsee
