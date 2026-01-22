let player={
    name:"Hardi",
    chips:245
}
let cards = []
let sum = 0
let hasBlackJack = false
let isAlive = false
let message = ""
let msgEl = document.getElementById("msg-el")
let sumEl = document.getElementById("sum-el")
let cardEl = document.getElementById("card-el")
let playerEl = document.getElementById("player-el")
 
playerEl.textContent= player.name+ ": $"+player.chips



console.log(cards)

function getrandomcard() {
    let randomNumber = Math.floor(Math.random() * 13) + 1
    if (randomNumber > 10) {
        return 10
    } else if (randomNumber === 11) {
        return 11
    } else {
        return randomNumber
    }
}
function startgame() {
    isAlive = true
    let firstcard = getrandomcard()
    let secondcard = getrandomcard()
    cards = [firstcard, secondcard]
    sum = firstcard + secondcard
    rendergame()
}
function rendergame() {
    cardEl.textContent = "cards:"

    for (let i = 0; i < cards.length; i++) {
        cardEl.textContent += cards[i] + " "
    }

    sumEl.textContent = "sum:" + sum
    if (sum < 21) {
        message = "do you want to draw a new card?"
    } else if (sum === 21) {
        message = "wohooo!you've got blackjack!"
        hasBlackJack = true
    } else if (sum > 21) {
        message = "you are out of the game"
        isAlive = false
    }
    msgEl.textContent = message
}

function newcard() {
    if (isAlive === true && hasBlackJack === false) {
        console.log("drawing a new card from the deck!")
        let card = getrandomcard()
        sum += card
        cards.push(card)
        console.log(card)
        rendergame()
    }

}





